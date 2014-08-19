#! /usr/bin/python
import os
import json
from autopilot.common import utils
from autopilot.common import exception


class GitInstallProvider(object):
    """
    Git install provider
    """
    def __init__(self, apenv, role, role_group_name, stack_name, working_dir):
        self.apenv = apenv
        self.role = role
        self.working_dir = working_dir
        self.stack_name = stack_name
        self.role_group_name = role_group_name

    def run(self, callback=None, synchronous=False, timeout=120):
        git_url = self.role.deploy.get('git')
        branch = self.role.deploy.get('branch')
        self._ensure_clean_working_dir()
        git_command = "git clone {0} {1} -b {2}".format(git_url, self.working_dir, branch)
        (return_code, out, error) = utils.subprocess_cmd(git_command)
        if return_code:
            raise exception.GitInstallProviderException("git clone failed to fetch: {0} \n Error: {1}"
                                                        .format(git_command, error))

        # try:
        #     return self._install()
        # except Exception as ex:
        #     raise exception.GitInstallProviderException("Error", inner_exception=ex)
        return self._install(callback=callback, synchronous=synchronous, timeout=timeout)

    def _ensure_clean_working_dir(self):
        utils.rmtree(self.working_dir)
        utils.mkdir(self.working_dir)

    def _build_env(self):
        d = dict(target=self.role.name, working_dir=self.working_dir)
        d.update(self.apenv.get("stack").get("stack_spec").todict())
        d.update(materialized=self.apenv.get("stack").get("materialized"))
        return json.dumps(d)

    def _install(self, callback, synchronous, timeout):
        return SafePythonModuleRunner().run(ap_env_json=self._build_env(),
                                            working_dir=self.working_dir,
                                            module_name=os.path.splitext(self.role.deploy.get('script'))[0])

        # temp_module_name = '{0}.{1}.{2}.{3}'.format(self.stack_name, self.role_group_name,
        #                                            self.role.name, self.role.version)


class SafePythonModuleRunner(object):
    """
    Loads user provider python scripts in a different process and runs
    desired actions
    """
    def run(self, ap_env_json, working_dir, module_name):

        # import imp
        # runmod = imp.load_source(module_name, module_path)
        # return runmod.install(env=env)
        env_tmp_file = os.path.join(working_dir, 'apenv.json')
        with open(env_tmp_file, 'w') as f:
            f.write(ap_env_json)
        command = "python -c \"import test; import json; import os; env=json.load(open('{1}')); import {2}; {2}.install(env=env)\"".format(ap_env_json, env_tmp_file, module_name)
        print command
        (return_code, out, error) = utils.subprocess_cmd(command, working_dir=working_dir)
        if return_code:
            raise exception.GitInstallProviderException("Install failed: {0}".format(error))
        return out