# Runtime CLI Probe Latest

- head_sha: `3bc78d7546e8481cc60fab6cee8c81e2e7b6e4d3`

## Context
```text
WECHAT_IMAGE=ghcr.io/nickrunning/wechat-selkies:0.0.16
state_dir=state-runtime-cli-probe
port_3001=ready
```

## Radium / browser processes
```text
    509 /opt/wechat/RadiumWMPF/runtime/WeChatAppEx --log-level=2 --lang=zh-CN --wechat-files-path=/config/<redacted> --product-id=1002 --wechat-sub-user-agent=MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCLinuxWechat(0xf2741108) --web-translate --client_version=4067692808 --wmpf_root_dir=/config/<redacted> --enable-applet-v3 --wmpf-drm-plugin-path --no-preload --mojo-platform-channel-handle=3
    520 /opt/wechat/RadiumWMPF/runtime/crashpad_handler --no-rate-limit --database=/config/<redacted> --annotation=ext_info={"app_call_name":"WeChatAppEx","app_name":"WeChatAppEx","app_path":"/opt/wechat/RadiumWMPF/runtime/WeChatAppEx","crash_notify":"0","main_thread_id":"509","module_name":"XWeb_linux","modules_dir":"/opt/wechat/RadiumWMPF/runtime","product":"WeChatAppEx","report_type":"9999","restart_app_cmd":"/opt/wechat/RadiumWMPF/runtime/WeChatAppEx --log-level=2 --lang=zh-CN --wechat-files-path=/config/<redacted> --product-id=1002 --wechat-sub-user-agent=MicroMessenger/7.0.20.1781(0x6700143B) WindowsWechat(0x63090a13) UnifiedPCLinuxWechat(0xf2741108) --web-translate --client_version=4067692808 --wmpf_root_dir=/config/<redacted> --enable-applet-v3 --wmpf-drm-plugin-path --no-preload --mojo-platform-channel-handle=3 --disable-notifications --enable-crash-reporter --enable-features=,OverlayScrollbar,XWorker,NetworkServiceMemoryCache --disable-features=DigitalGoodsApi,NotificationTriggers,PeriodicBackgroundSync,BackForwardCache,TFLiteLanguageDetectionEnabled,WebOTP,HardwareMediaKeyHandling,AudioServiceOutOfProcess,Vulkan,AutoupgradeMixedContent --wmpf_root_dir=/config/<redacted> --annotation=product=WeChatAppEx --initial-client-fd=103 --shared-client-connection
    529 /opt/wechat/RadiumWMPF/runtime/WeChatAppEx --type=zygote --no-zygote-sandbox --no-sandbox --log-level=2 --client_version=4067692808 --enable-crash-reporter --wmpf_root_dir=/config/<redacted> --crashpad-handler-pid=520 --product-id=1002
    530 /opt/wechat/RadiumWMPF/runtime/WeChatAppEx --type=zygote --no-sandbox --log-level=2 --client_version=4067692808 --enable-crash-reporter --wmpf_root_dir=/config/<redacted> --crashpad-handler-pid=520 --product-id=1002
    565 /opt/wechat/RadiumWMPF/runtime/WeChatAppEx --type=utility --utility-sub-type=network.mojom.NetworkService --lang=zh-CN --service-sandbox-type=none --no-sandbox --client_version=4067692808 --enable-crash-reporter --wmpf_root_dir=/config/<redacted> --crashpad-handler-pid=520 --product-id=1002 --disable-mojo-broker --shared-files=v8_context_snapshot_data:100 --field-trial-handle=3,i,16739182300980177406,7648773344531211900,262144 --enable-features=NetworkServiceMemoryCache,OverlayScrollbar,XWorker --disable-features=AudioServiceOutOfProcess,AutoupgradeMixedContent,BackForwardCache,DigitalGoodsApi,HardwareMediaKeyHandling,NotificationTriggers,PeriodicBackgroundSync,TFLiteLanguageDetectionEnabled,Vulkan,WebOTP --variations-seed-version --log-level=2
    605 /opt/wechat/RadiumWMPF/runtime/WeChatAppEx --type=gpu-process --no-sandbox --client_version=4067692808 --enable-crash-reporter --wmpf_root_dir=/config/<redacted> --crashpad-handler-pid=520 --product-id=1002 --gpu-preferences=WAAAAAAAAAAgAAAEAAAAAAAAAAAAAAAAAABgAAAAAAA4AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAABAAAAGAAAAAAAAAAYAAAAAAAAAAgAAAAAAAAACAAAAAAAAAAIAAAAAAAAAA== --use-gl=angle --use-angle=swiftshader-webgl --disable-mojo-broker --shared-files --field-trial-handle=3,i,16739182300980177406,7648773344531211900,262144 --enable-features=NetworkServiceMemoryCache,OverlayScrollbar,XWorker --disable-features=AudioServiceOutOfProcess,AutoupgradeMixedContent,BackForwardCache,DigitalGoodsApi,HardwareMediaKeyHandling,NotificationTriggers,PeriodicBackgroundSync,TFLiteLanguageDetectionEnabled,Vulkan,WebOTP --variations-seed-version --log-level=2
```

## Listening ports
```text
State  Recv-Q Send-Q Local Address:Port  Peer Address:PortProcess                        
LISTEN 0      4096      127.0.0.11:45207      0.0.0.0:*                                  
LISTEN 0      511          0.0.0.0:3000       0.0.0.0:*    users:(("nginx",pid=297,fd=5))
LISTEN 0      511          0.0.0.0:3001       0.0.0.0:*    users:(("nginx",pid=297,fd=7))
LISTEN 0      100          0.0.0.0:8082       0.0.0.0:*                                  
LISTEN 0      511             [::]:3000          [::]:*    users:(("nginx",pid=297,fd=6))
LISTEN 0      511             [::]:3001          [::]:*    users:(("nginx",pid=297,fd=8))
```

## DevTools probe
```text
candidate_ports=9222,9223,9229,9333,9444
```

## Port 8082 probe
```text
base=http://127.0.0.1:8082
--- ownership ---
--- http ---
ENDPOINT /
ENDPOINT /json/version
ENDPOINT /json/list
ENDPOINT /health
ENDPOINT /metrics
```

## Runtime configuration hints
```text
/etc/s6-overlay/s6-rc.d/init-nginx/run:9:CWS="${CUSTOM_WS_PORT:-8082}"
/etc/s6-overlay/s6-rc.d/init-selkies-config/run:306:  printf "8082" > /run/s6/container_environment/CUSTOM_WS_PORT
/etc/nginx/sites-available/default:39:    proxy_pass              http://127.0.0.1:8082;
/etc/nginx/sites-available/default:97:    proxy_pass              http://127.0.0.1:8082;
```

## X11 capability
```text
DISPLAY=:1
--- commands ---
xdotool=/usr/bin/xdotool
xprop=/usr/bin/xprop
xclip=/usr/bin/xclip
--- visible wechat windows ---
WINDOW_INDEX=1
WINDOW=16777222
X=371
Y=193
WIDTH=281
HEIGHT=381
SCREEN=0
NAME=<redacted>
WM_CLASS(STRING) = "wechat", "wechat"
_NET_WM_NAME=<redacted>
WM_NAME=<redacted>
WECHAT_WINDOWS=1
```

## URL handler capability
```text
--- desktop candidates ---
DESKTOP_DISCOVERED=/usr/share/applications/wechat.desktop
Name=wechat
Exec=/usr/bin/wechat %U
--- x-scheme-handler/weixin ---
--- registrations ---
--- executable strings hints ---
```
