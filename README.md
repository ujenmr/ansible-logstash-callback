# Ansible Logstash Callback Plugin

ansible.cfg:
```
    callback_plugins   = <path_to_callback_plugins_folder>
    callback_whitelist = logstash
```

Put the plugin in <path_to_callback_plugins_folder>

logstash config:
```
input {
    tcp {
        port => 5000
        codec => json
    }
}
```

This plugin makes use of the following environment variables:
    LOGSTASH_SERVER   (optional): defaults to localhost
    LOGSTASH_PORT     (optional): defaults to 5000
    LOGSTASH_TYPE     (optional): defaults to ansible
