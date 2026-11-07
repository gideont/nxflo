FROM python:3.12-alpine AS builder
WORKDIR /site
COPY build.py styles.css script.js *.html ./
COPY lib ./lib
COPY images ./images
COPY fonts ./fonts
COPY articles ./articles
COPY tools ./tools
COPY bms_integration_hub/index.html bms_integration_hub/portal.css bms_integration_hub/portal.js bms_integration_hub/dashboard.css bms_integration_hub/dashboard.js bms_integration_hub/icons.svg bms_integration_hub/LUCIDE-LICENSE.txt ./bms_integration_hub/
RUN python build.py --output /site/dist

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /site/dist/ /usr/share/nginx/html/
EXPOSE 80
