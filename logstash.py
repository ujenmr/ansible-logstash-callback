# (C) 2016, Ievgen Khmelenko <ujenmr@gmail.com>
#
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

import os
import json
import socket
import uuid

import logging

try:
    import logstash
    HAS_LOGSTASH = True
except ImportError:
    HAS_LOGSTASH = False

from ansible.plugins.callback import CallbackBase

class CallbackModule(CallbackBase):
    """
    ansible logstash callback plugin
    ansible.cfg:
        callback_plugins   = <path_to_callback_plugins_folder>
        callback_whitelist = logstash
    and put the plugin in <path_to_callback_plugins_folder>

    logstash config:
        input {
            tcp {
                port => 5000
                codec => json
            }
        }

    Requires:
        python-logstash

    This plugin makes use of the following environment variables:
        LOGSTASH_SERVER      (optional): defaults is "localhost"
        LOGSTASH_PORT        (optional): defaults is "5000"
        LOGSTASH_TYPE        (optional): defaults is "ansible"
        LOGSTASH_PRE_COMMAND (optional): defaults is "ansible --version | head -1" execute command before run and result put ansible_pre_command_output field
    """
    CALLBACK_VERSION = 2.0
    CALLBACK_TYPE = 'aggregate'
    CALLBACK_NAME = 'logstash'
    CALLBACK_NEEDS_WHITELIST = True

    def __init__(self):
        super(CallbackModule, self).__init__()

        if not HAS_LOGSTASH:
            self.disabled = True
            self._display.warning("The required python-logstash is not installed. "
                "pip install python-logstash")
        else:
            self.logger =  logging.getLogger('python-logstash-logger')
            self.logger.setLevel(logging.DEBUG)

            self.handler = logstash.TCPLogstashHandler(
                os.getenv('LOGSTASH_SERVER', 'localhost'),
                int(os.getenv('LOGSTASH_PORT', 5000)),
                version=1,
                message_type=os.getenv('LOGSTASH_TYPE', 'ansible')
            )

            self.logger.addHandler(self.handler)
            self.hostname = socket.gethostname()
            self.session = str(uuid.uuid1())
            self.pre_command_output = os.popen(os.getenv("LOGSTASH_PRE_COMMAND", "ansible --version | head -1 | tr '\n' ' ' | sed -e 's/ansible//gI' -e 's/[[:space:]]//g'")).read()
            self.errors = 0

    def v2_playbook_on_start(self, playbook):
        self.playbook = playbook._file_name
        data = {
            'status': "OK",
            'host': self.hostname,
            'session': self.session,
            'ansible_type': "start",
            'ansible_playbook': self.playbook,
        }
        self.logger.info("START " + self.playbook, extra = data)

    def v2_playbook_on_stats(self, stats):
        summarize_stat = {}
        for host in stats.processed.keys():
            summarize_stat[host] = stats.summarize(host)

        if self.errors == 0:
            status = "OK"
        else:
            status = "FAILED"

        data = {
            'status': status,
            'host': self.hostname,
            'session': self.session,
            'ansible_type': "finish",
            'ansible_playbook': self.playbook,
            'ansible_pre_command_output': self.pre_command_output,
            'ansible_result': json.dumps(summarize_stat), # deprecated field
        }
        self.logger.info(json.dumps(summarize_stat), extra = data)

    def v2_playbook_on_play_start(self, play):
        self.play_id = str(play._uuid)

        """
        play.name, if not specified in the playbook, will use the value of the line containing the - (yaml indent)
        Example:

        ---
        - name: Play 1
          hosts: all
          roles:
            - whatever.thing

        - hosts: localhost
          connection: local
          roles:
            - whatever.thing
        ...

        would produce play.name of "Play 1" and "localhost"
        """
        if play.name:
            self.play_name = play.name

        data = {
            'status': "OK",
            'host': self.hostname,
            'session': self.session,
            'ansible_type': "start",
            'ansible_playbook': self.playbook,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
        }

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.task_id = str(task._uuid)

    '''
    Tasks and handler tasks are dealt with here
    '''
    def v2_runner_on_ok(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ','')
        task_name = str(result._task).replace('HANDLER: ','')
        if task_name == 'setup':
            data = {
                'status': "OK",
                'host': self.hostname,
                'session': self.session,
                'ansible_play_id': self.play_id,
                'ansible_play_name': self.play_name,
                'ansible_type': "setup",
                'ansible_playbook': self.playbook,
                'ansible_host': result._host.name,
                'ansible_task': task_name,
                'ansible_pre_command_output': self.pre_command_output,
                'ansible_facts': self._dump_results(result._result) # deprecated field
            }
        else:
            if 'changed' in result._result.keys():
                changed = result._result['changed']
            else:
                changed = False
            data = {
                'status': "OK",
                'host': self.hostname,
                'session': self.session,
                'ansible_play_id': self.play_id,
                'ansible_play_name': self.play_name,
                'ansible_changed': changed,
                'ansible_type': "task",
                'ansible_playbook': self.playbook,
                'ansible_host': result._host.name,
                'ansible_task': task_name,
                'ansible_task_id': self.task_id,
                'ansible_pre_command_output': self.pre_command_output,
                'ansible_result': self._dump_results(result._result) # deprecated field
            }
        self.logger.info(self._dump_results(result._result), extra = data)

    def v2_runner_on_skipped(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ','')
        data = {
            'status': "SKIPPED",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_type': "task",
            'ansible_playbook': self.playbook,
            'ansible_task': task_name,
            'ansible_task_id': self.task_id,
            'ansible_pre_command_output': self.pre_command_output,
            'ansible_host': result._host.name
        }
        self.logger.info("SKIPPED " + task_name, extra = data)

    def v2_playbook_on_import_for_host(self, result, imported_file):
        data = {
            'status': "IMPORTED",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_type': "import",
            'ansible_playbook': self.playbook,
            'ansible_host': result._host.name,
            'ansible_pre_command_output': self.pre_command_output,
            'imported_file': imported_file
        }
        self.logger.info("IMPORT " + imported_file, extra = data)

    def v2_playbook_on_not_import_for_host(self, result, missing_file):
        data = {
            'status': "NOT IMPORTED",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_type': "import",
            'ansible_playbook': self.playbook,
            'ansible_host': result._host.name,
            'ansible_pre_command_output': self.pre_command_output,
            'missing_file': missing_file
        }
        self.logger.info("NOT IMPORTED " + missing_file, extra = data)

    def v2_runner_on_failed(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ','')
        if 'changed' in result._result.keys():
            changed = result._result['changed']
        else:
            changed = False
        data = {
            'status': "FAILED",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_changed': changed,
            'ansible_type': "task",
            'ansible_playbook': self.playbook,
            'ansible_host': result._host.name,
            'ansible_task': task_name,
            'ansible_task_id': self.task_id,
            'ansible_pre_command_output': self.pre_command_output,
            'ansible_result': self._dump_results(result._result) # deprecated field
        }
        self.errors += 1
        self.logger.error(self._dump_results(result._result), extra = data)

    def v2_runner_on_unreachable(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ','')
        data = {
            'status': "UNREACHABLE",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_type': "task",
            'ansible_playbook': self.playbook,
            'ansible_host': result._host.name,
            'ansible_task': task_name,
            'ansible_task_id': self.task_id,
            'ansible_pre_command_output': self.pre_command_output,
            'ansible_result': self._dump_results(result._result) # deprecated field
        }
        self.logger.error(self._dump_results(result._result), extra = data)

    def v2_runner_on_async_failed(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ','')
        data = {
            'status': "FAILED",
            'host': self.hostname,
            'session': self.session,
            'ansible_play_id': self.play_id,
            'ansible_play_name': self.play_name,
            'ansible_type': "task",
            'ansible_playbook': self.playbook,
            'ansible_host': result._host.name,
            'ansible_task': task_name,
            'ansible_task_id': self.task_id,
            'ansible_pre_command_output': self.pre_command_output,
            'ansible_result': self._dump_results(result._result) # deprecated field
        }
        self.errors += 1
        self.logger.error(self._dump_results(result._result), extra = data)
