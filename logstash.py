# (C) 2018, Yevhen Khmelenko <ujenmr@gmail.com>
# (C) 2017 Ansible Project
# GNU General Public License v3.0+ (see COPYING or https://www.gnu.org/licenses/gpl-3.0.txt)

from __future__ import (absolute_import, division, print_function)
__metaclass__ = type

DOCUMENTATION = '''
    callback: logstash
    type: notification
    author: Yevhen Khmelenko <ujenmr@gmail.com>
    short_description: Sends events to Logstash
    description:
      - This callback will report facts and task events to Logstash https://www.elastic.co/products/logstash
    version_added: "2.3"
    requirements:
      - whitelisting in configuration
      - logstash (python library)
    options:
      server:
        description: Address of the Logstash server
        env:
          - name: LOGSTASH_SERVER
        default: localhost
      port:
        description: Port on which logstash is listening
        env:
          - name: LOGSTASH_PORT
        default: 5000
      pre_command:
        description: Executes command before run and result put to ansible_pre_command_output field
        env:
          - name: LOGSTASH_PRE_COMMAND
        default: "ansible --version | head -1"
      type:
        description: Message type
        env:
          - name: LOGSTASH_TYPE
        default: ansible
'''

import os
import json
import socket
import uuid
import logging
from datetime import datetime

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
        callback_whitelist = logstash

    logstash config:
        input {
            tcp {
                port => 5000
                codec => json
            }
        }

    Requires:
        python-logstash
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
        self.start_time = datetime.utcnow()

    def v2_playbook_on_start(self, playbook):
        data = self.base_data.copy()
        data['ansible_type'] = "start"
        data['status'] = "OK"
        data['ansible_playbook'] = playbook._file_name
        self.logger.info("START PLAYBOOK | " + data['ansible_playbook'], extra=data)

    def v2_playbook_on_stats(self, stats):
        end_time = datetime.utcnow()
        runtime = end_time - self.start_time
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
        data['ansible_playbook_duration'] = runtime.total_seconds()
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
