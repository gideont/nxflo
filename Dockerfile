FROM python:3.12-alpine AS builder
WORKDIR /site
COPY build.py styles.css script.js *.html ./
COPY lib ./lib
COPY images ./images
RUN python build.py --output /site/dist

FROM nginx:alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /site/dist/ /usr/share/nginx/html/
EXPOSE 80
