FROM node:22-alpine

# git: baileys trae libsignal como dependencia desde GitHub.
RUN apk add --no-cache ffmpeg git

WORKDIR /app
COPY package*.json ./
RUN npm install
COPY tsconfig.json ./
COPY src ./src
COPY assets ./assets
RUN npm run build

CMD ["node", "dist/index.js"]
