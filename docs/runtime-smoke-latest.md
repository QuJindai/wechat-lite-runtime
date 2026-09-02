# Runtime Smoke Latest

- head_sha: `3d546d8c3b288ece49e58e24ff52b4efd5f340c9`
- validate_compose: `success`
- start_services: `failure`
- probe_workspace_localhost_3001: `skipped`

## Compose validation stderr
```text
```

## Compose start stderr
```text
 wechat Pulling 
 workspace Pulling 
 c19952135643 Pulling fs layer 
 7bbf972c6c2f Pulling fs layer 
 900e2c02f17f Pulling fs layer 
 abe9c1abe6f3 Pulling fs layer 
 6cba66ca3410 Pulling fs layer 
 88adae806875 Pulling fs layer 
 71d58a2f05b2 Pulling fs layer 
 b3aa348678a1 Pulling fs layer 
 147b7e13a61f Pulling fs layer 
 92e7a315d167 Pulling fs layer 
 e8b51ce0d0f7 Pulling fs layer 
 552b94a43e8b Pulling fs layer 
 462856c69d90 Pulling fs layer 
 3ea645c2d7aa Pulling fs layer 
 a648aca30351 Pulling fs layer 
 b4b4e6304c05 Pulling fs layer 
 3528df54205e Pulling fs layer 
 abe9c1abe6f3 Waiting 
 6cba66ca3410 Waiting 
 88adae806875 Waiting 
 71d58a2f05b2 Waiting 
 b3aa348678a1 Waiting 
 147b7e13a61f Waiting 
 92e7a315d167 Waiting 
 a648aca30351 Waiting 
 e8b51ce0d0f7 Waiting 
 b4b4e6304c05 Waiting 
 552b94a43e8b Waiting 
 3ea645c2d7aa Waiting 
 3528df54205e Waiting 
 462856c69d90 Waiting 
 900e2c02f17f Downloading [>                                                  ]  538.7kB/64.4MB
 7bbf972c6c2f Downloading [>                                                  ]  243.8kB/24.02MB
 c19952135643 Downloading [>                                                  ]  489.6kB/48.49MB
 900e2c02f17f Downloading [====================>                              ]  25.94MB/64.4MB
 7bbf972c6c2f Downloading [===================================>               ]  16.96MB/24.02MB
 7bbf972c6c2f Verifying Checksum 
 7bbf972c6c2f Download complete 
 900e2c02f17f Downloading [=======================================>           ]  50.81MB/64.4MB
 c19952135643 Downloading [==================>                                ]  17.69MB/48.49MB
 abe9c1abe6f3 Downloading [>                                                  ]  538.7kB/211.4MB
 wechat Error manifest unknown
Error response from daemon: manifest unknown
```

## Container state
```text
NAME      IMAGE     COMMAND   SERVICE   CREATED   STATUS    PORTS
```
