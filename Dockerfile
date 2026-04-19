FROM node:20-slim

WORKDIR /app

COPY api/package*.json ./
RUN npm ci --omit=dev && npm cache clean --force

COPY api/ ./

EXPOSE 8000

CMD ["node", "app.js"]
