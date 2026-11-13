FROM nginx:stable-alpine

# Nginx listens on an unprivileged port and runs as the unprivileged nginx user.
COPY nginx.conf /etc/nginx/nginx.conf
RUN rm -f /etc/nginx/conf.d/default.conf \
    && chown -R 101:101 /var/cache/nginx

USER 101:101
EXPOSE 8080
ENTRYPOINT ["nginx"]
CMD ["-g", "daemon off;"]
