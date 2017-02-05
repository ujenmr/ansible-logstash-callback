# Ansible Logstash Callback Plugin
This repository provides a callback plugin that ships Ansible output via Logstash to an indexer as configured via Logstash.

### Ansible section
Install python-logstash
```
pip install python-logstash
```

Append the following to the `[defaults]` section of your `ansible.cfg`
```
    callback_plugins   = <path_to_callback_plugins_folder>
    callback_whitelist = logstash
```

Put the `logstash` plugin from this git repository into the path_to_callback_plugins_folder as defined above.

This plugin makes use of the following environment variables:
* `LOGSTASH_SERVER`   (optional): defaults to localhost
* `LOGSTASH_PORT`     (optional): defaults to 5000
* `LOGSTASH_TYPE`     (optional): defaults to ansible

### Logstash section

Basic logstash testing config
```
input {
    tcp {
        port => 5000
        codec => json
    }
}
```

Shipping logs to elasticsearch
```
input {
    tcp {
        port => 5000
        codec => json
    }
}
output {
    elasticsearch {
        hosts => ["localhost:9200"]
    }
    stdout {
        codec => rubydebug
    }
}
```

### Elasticsearch
This repository contains a file titled `ansible.template`. This template can be loaded into your elasticsearch cluster to provide a nice mapping for the ansible data.

List available templates
```
curl -s -XGET localhost:9200/_template
```

Load the template
```
curl -s -XPUT 'http://localhost:9200/_template/ansible' -d@ansible.template
```

- - - -

# Example Usage and Output
This is just an example of how to use the environment variables when running a playbook.

```
LOGSTASH_SERVER=127.0.0.1 LOGSTASH_PORT=5000 ansible-playbook playbook.yml
```

Logstash Output
```
{
        "ansible_type" => "start",
               "level" => "INFO",
             "session" => "111f73e0-eb57-11e6-bc8d-e4115b24f077",
             "message" => "START playbooks/deploy-aws-bastion.yml",
                "type" => "ansible",
    "ansible_playbook" => "playbooks/deploy-aws-bastion.yml",
                "tags" => [],
                "path" => "/opt/work/ansible-playbook-bastion/ansible/plugins/callbacks/logstash-latest.py",
          "@timestamp" => 2017-02-05T03:56:26.335Z,
                "port" => 43920,
            "@version" => "1",
                "host" => "laptappy",
         "logger_name" => "python-logstash-logger",
              "status" => "OK"
}
{
        "ansible_type" => "task",
               "level" => "INFO",
      "ansible_result" => "{\"changed\": false, \"cmd\": \"TZ=':US/Eastern' date +%s\", \"delta\": \"0:00:00.003644\", \"end\": \"2017-02-05 03:56:57.823829\", \"rc\": 0, \"start\": \"2017-02-05 03:56:57.820185\", \"stderr\": \"\", \"stdout\": \"1486267017\", \"stdout_lines\": [\"1486267017\"], \"warnings\": []}",
             "session" => "111f73e0-eb57-11e6-bc8d-e4115b24f077",
     "ansible_changed" => false,
             "message" => "{\"changed\": false, \"cmd\": \"TZ=':US/Eastern' date +%s\", \"delta\": \"0:00:00.003644\", \"end\": \"2017-02-05 03:56:57.823829\", \"rc\": 0, \"start\": \"2017-02-05 03:56:57.820185\", \"stderr\": \"\", \"stdout\": \"1486267017\", \"stdout_lines\": [\"1486267017\"], \"warnings\": []}",
                "type" => "ansible",
    "ansible_playbook" => "playbooks/deploy-aws-bastion.yml",
        "ansible_task" => "Get post-epoch time",
                "tags" => [],
                "path" => "/opt/work/ansible-playbook-bastion/ansible/plugins/callbacks/logstash-latest.py",
        "ansible_host" => "172.17.0.27",
          "@timestamp" => 2017-02-05T03:56:57.855Z,
                "port" => 43920,
                "host" => "laptappy",
            "@version" => "1",
         "logger_name" => "python-logstash-logger",
              "status" => "OK"
}
{
        "ansible_type" => "finish",
               "level" => "INFO",
      "ansible_result" => "{\"172.17.0.27\": {\"unreachable\": 0, \"skipped\": 2, \"ok\": 15, \"changed\": 0, \"failures\": 0}}",
             "session" => "111f73e0-eb57-11e6-bc8d-e4115b24f077",
             "message" => "{\"172.17.0.27\": {\"unreachable\": 0, \"skipped\": 2, \"ok\": 15, \"changed\": 0, \"failures\": 0}}",
                "type" => "ansible",
    "ansible_playbook" => "playbooks/deploy-aws-bastion.yml",
                "tags" => [],
                "path" => "/opt/work/ansible-playbook-bastion/ansible/plugins/callbacks/logstash-latest.py",
          "@timestamp" => 2017-02-05T03:56:57.857Z,
                "port" => 43920,
            "@version" => "1",
                "host" => "laptappy",
         "logger_name" => "python-logstash-logger",
              "status" => "OK"
}
```
