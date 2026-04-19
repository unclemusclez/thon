# Nginx Template Reference: Port-Based Reverse Proxy
#
# A single combined server block with one location per sandbox instance.
# The location path mirrors the server-returned endpoint path:
#
#   host mode:   endpoint 127.0.0.1:8443             -> location /8443/              -> proxy_pass http://127.0.0.1:8443/
#   bridge mode: endpoint 127.0.0.1:55002/proxy/8443  -> location /55002/proxy/8443/  -> proxy_pass http://127.0.0.1:55002/proxy/8443/
#
# Outside users access via https://{eip}/{location_path}
#
# Example (bridge mode, 2 users):

server {
    listen 80;
    listen 443 ssl;
    listen [::]:443 ssl;
    server_name _;

    ssl_certificate /etc/nginx/ssl/port-8443.crt;
    ssl_certificate_key /etc/nginx/ssl/port-8443.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    location /55002/proxy/8443/ {
        proxy_pass http://127.0.0.1:55002/proxy/8443/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
        add_header Service-Worker-Allowed /;
        proxy_ssl_verify off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
        proxy_request_buffering off;
    }

    location /54581/proxy/8444/ {
        proxy_pass http://127.0.0.1:54581/proxy/8444/;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Proto https;
        proxy_redirect off;
        add_header Service-Worker-Allowed /;
        proxy_ssl_verify off;
        proxy_read_timeout 86400;
        proxy_send_timeout 86400;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
