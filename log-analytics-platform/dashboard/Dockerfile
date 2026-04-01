FROM node:18-alpine AS build

WORKDIR /app
COPY package.json ./
RUN npm install --legacy-peer-deps && \
    npm ls ajv || true
COPY public/ public/
COPY src/ src/

ENV REACT_APP_API_URL=http://localhost:8000
ENV REACT_APP_WS_URL=ws://localhost:8000
ENV DISABLE_ESLINT_PLUGIN=true

RUN npm run build

FROM nginx:alpine
COPY --from=build /app/build /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
