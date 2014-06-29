#! /user/bin python

import time
from autopilot.common import exception
from autopilot.common.utils import Dct
from autopilot.common.asyncpool import taskpool
from autopilot.inf.inf import Inf, InfResponseContext
from autopilot.inf.aws import awsutils
from autopilot.inf.aws import awsexception


class AWSInfResponseContext(InfResponseContext):
    def __init__(self, aws_inf, spec):
        """
        Response context base class for tracking AWS resquests
        """
        InfResponseContext.__init__(self, spec)


class AwsInfProvisionResponseContext(AWSInfResponseContext):
    """
    Response Context object to track AWS instance provisioning requests
    """
    def __init__(self, aws_inf, spec, reservation):
        AWSInfResponseContext.__init__(self, aws_inf=aws_inf, spec=spec)
        self.reservation = reservation

    def all_instances_in_state(self, state="running"):
        for instance in self.reservation.instances:
            instance.update()
            # if any instance is pending return True
            if instance.state != state:
                return False
        return True

    def close_on_instances_ready(self, timeout=180, interval=10):
        """
        Close when all instances are running
        """
        if self.yield_until_instances_in_state(timeout=timeout, interval=interval):
            self.close()
        else:
            self.close(new_errors=[exception.AWSInstanceProvisionTimeout(self.reservation.instances)])

    def yield_until_instances_in_state(self, state="running", timeout=180, interval=10):
        """
        Yield until all instances are in a specified state
        """
        max_tries = timeout/interval
        attempt = 0
        while attempt < max_tries:
            attempt += 1
            if not self.all_instances_in_state(state=state):
                taskpool.doyield(time_in_seconds=interval)
            else:
                return True
        return False


class AWSInf(Inf):
    """
    AWS Infrastructure management functions

    All wait and test actions following aws api calls are all pumped through the gevent and
    should yield if we have monkey patched somewhere along the call chain.
    """
    def __init__(self, aws_access_key=None, aws_secret_key=None):
        Inf.__init__(self)
        self.aws_access_key = aws_access_key
        self.aws_secret_key = aws_secret_key
        self.vpc_conn = self._get_vpc()
        self.ec2_conn = self._get_ec2()

    def init_domain(self, domain_spec={}):
        """
        Create a private cluster environment based on the spec.
        At minimum this will create:
        1. VPC
        2. Internet gateway with internet routing enabled and attach to the VPC
        """
        rc = AWSInfResponseContext(aws_inf=self, spec=domain_spec)
        try:
            # create a vpc and a default internet gateway
            data = self.vpc_conn.create_vpc(cidr_block=Dct.get(domain_spec, "cidr", "10.0.0.0/16"))
            domain_spec["vpc_id"] = data["vpc"].id
            domain_spec["internet_gateway_id"] = data["internet_gateway"].id
            domain_spec["subnets"] = []
        except Exception, e:
            rc.errors.extend(e)

        # return updated spec
        rc.close(new_spec=domain_spec)
        return rc

    def init_stack(self, stack_spec={}):
        """
        We need a VPC in the role_spec that we can use
        Create a subnet for the role with route tables and security groups
        """
        rc = AWSInfResponseContext(aws_inf=self, spec=stack_spec)
        if not Dct.contains_key(stack_spec, "vpc_id"):
            raise awsexception.VPCDoesNotExists()

        try:
            subnets = Dct.get(stack_spec, "subnets")

            # create a subnet for this within the vpc
            data = self.vpc_conn.create_subnet(vpc_id=stack_spec["vpc_id"], cidr_block=Dct.get(stack_spec, "cidr", "10.0.0.0/24"),
                                               new_route_table=True, gateway_id=stack_spec["internet_gateway_id"],
                                               open_route_to_gateway=True)
            new_subnet = {"subnet_id":  data["subnet"].id, "route_table_id": data["route_table"].id,
                          "route_association_id": data["route_association_id"]}

            subnets.append(new_subnet)

        except Exception, e:
            rc.errors.extend(e)

        # return updated spec
        rc.close(new_spec=stack_spec)
        return rc

    def delete_domain(self, domain_spec={}, delete_dependencies=False):
        """
        Delete the cluster
        """
        self.vpc_conn.delete_vpc(vpc_id=Dct.get(domain_spec, "vpc_id"), force=delete_dependencies)

    def provision_role(self, role_spec={}, tags=[]):
        """
        We need a subnet in the the instance_spec
        1. Create default security group with inbound traffic for:
            a. 22-22 (0.0.0.0/0)
            b. Custom auth_spec
        2. Provision a set of machines asynchronously as per spec.
        Returns a AWSInfRequestContext context
        """

        # required parameters
        uname = Dct.get(role_spec, "uname")
        image_id = Dct.get(role_spec, "image_id")
        instance_type = Dct.get(role_spec, "instance_type")
        key_pair_name = Dct.get(role_spec, "key_pair_name")
        vpc_id = Dct.get(role_spec, "vpc_id")
        subnet_id = Dct.get(role_spec, "subnet_id")
        instance_count = Dct.get(role_spec, "instance_count")
        associate_public_ip = Dct.get(role_spec, "associate_public_ip", False)

        # create a security group
        sg = self.ec2_conn.create_group("sg_{0}".format(uname),
                                        description="security group for {0}".format(uname),
                                        auth_ssh=True, vpc_id=vpc_id,
                                        auth_spec=Dct.get(role_spec, "auth_spec"))

        role_spec["security_group_ids"] = [sg.id]

        # schedule instance creation.
        reservation = self.ec2_conn.request_instances(image_id=image_id,
                                                      instance_type=instance_type,
                                                      key_name=key_pair_name,
                                                      max_count=instance_count,
                                                      security_group_ids=role_spec["security_group_ids"],
                                                      subnet_id=subnet_id,
                                                      associate_public_ip=associate_public_ip)

        role_spec["instances"] = reservation.instances

        # create a response context
        rc = AwsInfProvisionResponseContext(aws_inf=self, spec=role_spec, reservation=reservation)
        rc.close_on_instances_ready()

        # return the context
        return rc

    def get_stack_status(self, stack_spec):
        pass

    def _get_ec2(self):
        return awsutils.EasyEC2(aws_access_key_id = self.aws_access_key,
                                aws_secret_access_key = self.aws_secret_key, aws_region_name="us-east-1")

    def _get_vpc(self):
        return awsutils.EasyVPC(aws_access_key_id=self.aws_access_key,
                                aws_secret_access_key=self.aws_secret_key, aws_region_name="us-east-1")