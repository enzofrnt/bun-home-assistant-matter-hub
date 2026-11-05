#!/usr/bin/with-contenv bashio

# Bun uses JavaScriptCore; V8 heap flags have no effect on this runtime.
if [ "$(bashio::config 'heap_size_mb' '0')" != "0" ]; then
  bashio::log.info "Bun manages its heap automatically; the legacy heap_size_mb option is ignored."
fi
export APP_VERSION="${APP_VERSION:-$(bashio::addon.version)}"

exec home-assistant-matter-hub start \
  --log-level=$(bashio::config 'app_log_level') \
  --protocol-log-level=$(bashio::config 'protocol_log_level' 'info') \
  --disable-log-colors=$(bashio::config 'disable_log_colors') \
  --mdns-disable-ipv4=$(bashio::config 'mdns_disable_ipv4' 'false') \
  --mdns-network-interface="$(bashio::config 'mdns_network_interface')" \
  --mdns-strip-global-ipv6=$(bashio::config 'mdns_strip_global_ipv6' 'false') \
  --storage-location=/config/data \
  --web-port=$(bashio::addon.ingress_port) \
  --home-assistant-url='http://supervisor/core' \
  --home-assistant-access-token="$SUPERVISOR_TOKEN" \
  --http-ip-whitelist="172.30.32.2"
