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

try:
    from __main__ import cli
except ImportError:
    # using API w/o cli
    cli = False

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
            self.logger = logging.getLogger('python-logstash-logger')
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
            self.pre_command_output = os.popen(os.getenv(
                "LOGSTASH_PRE_COMMAND", "ansible --version | head -1")).read()
            self.errors = 0

            self.base_data = {
                'session': self.session,
                'ansible_pre_command_output': self.pre_command_output,
                'host': self.hostname
            }

            self.options = {}
            if cli:
                self._options = cli.options
                self.base_data['ansible_checkmode'] = self._options.check
                self.base_data['ansible_tags'] = self._options.tags
                self.base_data['ansible_skip_tags'] = self._options.skip_tags
                self.base_data['inventory'] = self._options.inventory

    def v2_playbook_on_start(self, playbook):
        data = self.base_data.copy()
        data['ansible_type'] = "start"
        data['status'] = "OK"
        data['ansible_playbook'] = playbook._file_name
        self.logger.info("START PLAYBOOK | " + data['ansible_playbook'], extra=data)

    def v2_playbook_on_stats(self, stats):
        summarize_stat = {}
        for host in stats.processed.keys():
            summarize_stat[host] = stats.summarize(host)

        if self.errors == 0:
            status = "OK"
        else:
            status = "FAILED"

        data = self.base_data.copy()
        data['ansible_type'] = "finish"
        data['status'] = status
        data['ansible_result'] = json.dumps(summarize_stat)  # deprecated field

        self.logger.info("FINISH PLAYBOOK | " + json.dumps(summarize_stat), extra=data)

    def v2_playbook_on_play_start(self, play):
        self.play_id = str(play._uuid)

        if play.name:
            self.play_name = play.name

        data = self.base_data.copy()
        data['ansible_type'] = "start"
        data['status'] = "OK"
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name

        self.logger.info("START PLAY | " + self.play_name, extra=data)

    def v2_playbook_on_task_start(self, task, is_conditional):
        self.task_id = str(task._uuid)

    '''
    Tasks and handler tasks are dealt with here
    '''

    def v2_runner_on_ok(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ', '').replace('HANDLER: ', '')

        data = self.base_data.copy()
        if task_name == 'setup':
            data['ansible_type'] = "setup"
            data['status'] = "OK"
            data['ansible_host'] = result._host.name
            data['ansible_play_id'] = self.play_id
            data['ansible_play_name'] = self.play_name
            data['ansible_task'] = task_name
            data['ansible_facts'] = self._dump_results(result._result)

            self.logger.info("SETUP FACTS | " + self._dump_results(result._result), extra=data)
        else:
            if 'changed' in result._result.keys():
                data['ansible_changed'] = result._result['changed']
            else:
                data['ansible_changed'] = False

            data['ansible_type'] = "task"
            data['status'] = "OK"
            data['ansible_host'] = result._host.name
            data['ansible_play_id'] = self.play_id
            data['ansible_play_name'] = self.play_name
            data['ansible_task'] = task_name
            data['ansible_task_id'] = self.task_id
            data['ansible_result'] = self._dump_results(result._result)

            self.logger.info("TASK OK | " + task_name + " | RESULT |  " + self._dump_results(result._result), extra=data)

    def v2_runner_on_skipped(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ', '').replace('HANDLER: ', '')

        data = self.base_data.copy()
        data['ansible_type'] = "task"
        data['status'] = "SKIPPED"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['ansible_task'] = task_name
        data['ansible_task_id'] = self.task_id
        data['ansible_result'] = self._dump_results(result._result)

        self.logger.info("TASK SKIPPED | " + task_name, extra=data)

    def v2_playbook_on_import_for_host(self, result, imported_file):
        data = self.base_data.copy()
        data['ansible_type'] = "import"
        data['status'] = "IMPORTED"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['imported_file'] = imported_file

        self.logger.info("IMPORT | " + imported_file, extra=data)

    def v2_playbook_on_not_import_for_host(self, result, missing_file):
        data = self.base_data.copy()
        data['ansible_type'] = "import"
        data['status'] = "NOT IMPORTED"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['imported_file'] = missing_file

        self.logger.info("NOT IMPORTED | " + missing_file, extra=data)

    def v2_runner_on_failed(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ', '').replace('HANDLER: ', '')

        data = self.base_data.copy()
        if 'changed' in result._result.keys():
            data['ansible_changed'] = result._result['changed']
        else:
            data['ansible_changed'] = False

        data['ansible_type'] = "task"
        data['status'] = "FAILED"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['ansible_task'] = task_name
        data['ansible_task_id'] = self.task_id
        data['ansible_result'] = self._dump_results(result._result)

        self.errors += 1
        self.logger.error("TASK FAILED | " + task_name + " | HOST | " + self.hostname +
            " | RESULT | " + self._dump_results(result._result), extra=data)

    def v2_runner_on_unreachable(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ', '').replace('HANDLER: ', '')

        data = self.base_data.copy()
        data['ansible_type'] = "task"
        data['status'] = "UNREACHABLE"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['ansible_task'] = task_name
        data['ansible_task_id'] = self.task_id
        data['ansible_result'] = self._dump_results(result._result)

        self.errors += 1
        self.logger.error("UNREACHABLE | " + task_name + " | HOST | " + self.hostname +
            " | RESULT | " + self._dump_results(result._result), extra=data)

    def v2_runner_on_async_failed(self, result, **kwargs):
        task_name = str(result._task).replace('TASK: ', '').replace('HANDLER: ', '')

        data = self.base_data.copy()
        data['ansible_type'] = "task"
        data['status'] = "FAILED"
        data['ansible_host'] = result._host.name
        data['ansible_play_id'] = self.play_id
        data['ansible_play_name'] = self.play_name
        data['ansible_task'] = task_name
        data['ansible_task_id'] = self.task_id
        data['ansible_result'] = self._dump_results(result._result)

        self.errors += 1
        self.logger.error("ASYNC FAILED | " + task_name + " | HOST | " + self.hostname +
            " | RESULT | " + self._dump_results(result._result), extra=data)
