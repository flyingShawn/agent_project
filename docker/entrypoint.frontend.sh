#!/bin/sh

CONFIG_FILE="/usr/share/nginx/html/config.js"

QUICK_OPTIONS_JSON="["
IFS=','
i=0
for item in $VITE_QUICK_OPTIONS; do
  if [ $i -gt 0 ]; then
    QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON},"
  fi
  QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON}\"${item}\""
  i=$((i + 1))
done
QUICK_OPTIONS_JSON="${QUICK_OPTIONS_JSON}]"

cat > "$CONFIG_FILE" << EOF
window.__APP_CONFIG__ = {
  appName: "${VITE_APP_NAME:-阳途智能助手}",
  subtitle: "${VITE_APP_SUBTITLE:-阳途智能助手为您服务}",
  welcomeText: "${VITE_APP_WELCOME_TEXT:-有什么我能帮您的呢？}",
  inputPlaceholder: "${VITE_APP_INPUT_PLACEHOLDER:-给智能助手发消息}",
  quickOptions: ${QUICK_OPTIONS_JSON}
};
EOF

echo "Generated config.js:"
cat "$CONFIG_FILE"

exec nginx -g 'daemon off;'
