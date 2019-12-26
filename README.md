# User Gudie

This project is implemented to mirror from a gitlab server to another.<br/>
It will create group and project in target gitlab automatically, so please grant the permission.

## Configuration

create a config.cfg and the content as the following

```
[global]
ssl_verify = false
api_version = 4
timeout = 5

[session_1]
url = http://private1.gitlab.com
private_token =

[session_2]
url = http://private2.gitlab.com
private_token =
```

To follow up the config.cfg, please revise the session id

```python
mirror = MirrorGitlab("session_1", "session_2")
```

## Execution

```bash
pip3 install -r requirements.txt
python3 app.py
```
