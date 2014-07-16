#! /usr/bin/python
import yaml


class Apspec(object):
    """
    Base class for ApSpec
    """
    def __init__(self, apenv, org, domain, type, inf=None, description=None):
        self.org = org
        self.domain = domain
        self.apenv = apenv
        self.type = type
        self.inf = inf
        self.description = description

    def todict(self):
        d = dict(org=self.org,
                 domain=self.domain,
                 type=self.type,
                 description=self.description)
        return dict(apspec=d)

    @staticmethod
    def load(apenv, org, domain, spec_stream):
        dct = yaml.load(spec_stream)
        spec_dct = dct.get('apspec')
        func = getattr(Apspec, "_resolve_{0}_spec".format(spec_dct.get('type')))
        return func(apenv, org, domain, spec_dct)

    @staticmethod
    def _resolve_roles_spec(apenv, org, domain, spec_dct):
        return Rolespec(apenv=apenv, org=org, domain=domain, type=spec_dct.get('type'),
                        description=spec_dct.get('description', None), rolesd=spec_dct.get("roles"))

    @staticmethod
    def _resolve_stack_spec(apenv, org, domain, spec_dct):
        return Stackspec(apenv=apenv, org=org, domain=domain, type=spec_dct.get('type'),
                         inf=spec_dct.get('infrastructure'), name=spec_dct.get('name'),
                         description=spec_dct.get('description'), groupsd=spec_dct.get("role-groups"))

class Rolespec(Apspec):
    """
    Define roles
    """
    def __init__(self, apenv, org, domain, type, description, rolesd):
        Apspec.__init__(self, apenv=apenv, org=org, domain=domain, type=type,
                        description=description)
        self.roles = Rolespec._resolve_roles(rolesd)

    def todict(self):
        d = Apspec.todict(self)
        d.update(roles={})
        for (role, val) in self.roles.items():
            d["roles"].update(val.todict())
        return d

    @staticmethod
    def _resolve_roles(rolesd):
        roles = {}
        for (role, val) in rolesd.items():
            roles[role] = Rolespec.Role(role, val.get('version'), val.get('deploy'))
        return roles

    class Role(object):
        def __init__(self, name, version, deploy):
            self.name = name
            self.version = version
            self.deploy = deploy

        def todict(self):
            return {self.name: dict(version=self.version, deploy=self.deploy)}


class Stackspec(Apspec):
    """
    Define the stack
    """
    def __init__(self, apenv, org, domain, type, inf, name, description, groupsd):
        Apspec.__init__(self, apenv=apenv, org=org, domain=domain, type=type, inf=inf, description=description)
        self.name = name
        self.groups = self._resolve_role_groups(groupsd)

    def _resolve_role_groups(self, groupsd):
        rg = {}
        for (group, val) in groupsd.items():
            rg[group] = Stackspec.Rolegroup(group, val)
        return rg


    class Rolegroup(object):
        def __init__(self, name, refsd={}):
            self.name = name
            self.rolerefs = {}
            for (role, val) in refsd.items():
                self.rolerefs[role] = Stackspec.RoleRef(role, val)

    class RoleRef(object):
        def __init__(self, name, refd):
            self.name = name
            self.instances = refd.get('instances')









