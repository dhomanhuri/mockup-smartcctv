FROM nginx:1.27-alpine

# The base image's own docker-entrypoint.d/20-envsubst-on-templates.sh
# hook envsubst's every *.template file under NGINX_ENVSUBST_TEMPLATE_DIR
# (default /etc/nginx/templates) at container start; redirecting its
# output dir here (default is /etc/nginx/conf.d, meant for nginx.conf
# templates) lets the same built-in mechanism generate config.js as a
# plain static file the pages load — see config.js.template and ADR-0016.
ENV NGINX_ENVSUBST_OUTPUT_DIR=/usr/share/nginx/html

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY config.js.template /etc/nginx/templates/config.js.template
COPY index.html /usr/share/nginx/html/index.html
COPY apd.html /usr/share/nginx/html/apd.html
COPY vehicle.html /usr/share/nginx/html/vehicle.html
COPY cases.html /usr/share/nginx/html/cases.html
COPY reports.html /usr/share/nginx/html/reports.html
COPY settings.html /usr/share/nginx/html/settings.html
COPY admin.html /usr/share/nginx/html/admin.html
COPY styles.css /usr/share/nginx/html/styles.css
COPY auth.js /usr/share/nginx/html/auth.js
COPY shell.js /usr/share/nginx/html/shell.js
COPY case-modal.js /usr/share/nginx/html/case-modal.js
COPY hls.min.js /usr/share/nginx/html/hls.min.js
COPY pertamina-ep-logo.jpg /usr/share/nginx/html/pertamina-ep-logo.jpg

EXPOSE 80
