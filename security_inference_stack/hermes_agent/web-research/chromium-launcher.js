'use strict';

const http = require('http');
const net = require('net');
const { chromium } = require('/app/node_modules/playwright');

const INTERNAL_CDP_PORT = 9223;
const EXTERNAL_CDP_PORT = 9222;
let browser;
let cdpProxy;
let shuttingDown = false;

function rewriteDebuggerUrls(buffer) {
  return Buffer.from(
    buffer
      .toString('utf8')
      .replaceAll(`ws://127.0.0.1:${INTERNAL_CDP_PORT}`, `ws://spider-chromium:${EXTERNAL_CDP_PORT}`)
      .replaceAll(`ws://localhost:${INTERNAL_CDP_PORT}`, `ws://spider-chromium:${EXTERNAL_CDP_PORT}`),
    'utf8',
  );
}

function startCdpProxy() {
  const server = http.createServer((request, response) => {
    const upstream = http.request(
      {
        host: '127.0.0.1',
        port: INTERNAL_CDP_PORT,
        method: request.method,
        path: request.url,
        headers: { ...request.headers, host: `127.0.0.1:${INTERNAL_CDP_PORT}` },
      },
      (upstreamResponse) => {
        const chunks = [];
        upstreamResponse.on('data', (chunk) => chunks.push(chunk));
        upstreamResponse.on('end', () => {
          const body = rewriteDebuggerUrls(Buffer.concat(chunks));
          const headers = { ...upstreamResponse.headers, 'content-length': String(body.length) };
          delete headers['transfer-encoding'];
          response.writeHead(upstreamResponse.statusCode || 502, headers);
          response.end(body);
        });
      },
    );
    upstream.on('error', (error) => {
      response.writeHead(502, { 'content-type': 'text/plain' });
      response.end(`CDP upstream unavailable: ${error.message}`);
    });
    request.pipe(upstream);
  });

  server.on('upgrade', (request, socket, head) => {
    const upstream = net.connect(INTERNAL_CDP_PORT, '127.0.0.1', () => {
      upstream.write(`${request.method} ${request.url} HTTP/${request.httpVersion}\r\n`);
      for (let index = 0; index < request.rawHeaders.length; index += 2) {
        if (request.rawHeaders[index].toLowerCase() !== 'host') {
          upstream.write(`${request.rawHeaders[index]}: ${request.rawHeaders[index + 1]}\r\n`);
        }
      }
      upstream.write(`Host: 127.0.0.1:${INTERNAL_CDP_PORT}\r\n`);
      upstream.write('\r\n');
      if (head.length) upstream.write(head);
      socket.pipe(upstream).pipe(socket);
    });
    upstream.on('error', () => socket.destroy());
    socket.on('error', () => upstream.destroy());
  });

  return new Promise((resolve, reject) => {
    server.once('error', reject);
    server.listen(EXTERNAL_CDP_PORT, '0.0.0.0', () => resolve(server));
  });
}

async function shutdown(signal) {
  if (shuttingDown) return;
  shuttingDown = true;
  try {
    if (cdpProxy) await new Promise((resolve) => cdpProxy.close(resolve));
    if (browser) await browser.close();
  } catch (error) {
    console.error(`Spider Chromium shutdown after ${signal} failed: ${error.message}`);
  }
  process.exit(0);
}

async function main() {
  browser = await chromium.launch({
    executablePath: '/ms-playwright/chromium-1232/chrome-linux64/chrome',
    headless: true,
    chromiumSandbox: false,
    proxy: {
      server: 'http://research-egress:3128',
      bypass: '<-loopback>',
    },
    args: [
      '--remote-debugging-address=127.0.0.1',
      `--remote-debugging-port=${INTERNAL_CDP_PORT}`,
      '--remote-allow-origins=*',
    ],
  });

  browser.on('disconnected', () => {
    if (!shuttingDown) {
      console.error('Spider Chromium disconnected unexpectedly');
      process.exit(1);
    }
  });

  cdpProxy = await startCdpProxy();
  console.log(`Spider Chromium CDP is ready on port ${EXTERNAL_CDP_PORT}`);
  await new Promise(() => {});
}

process.on('SIGTERM', () => void shutdown('SIGTERM'));
process.on('SIGINT', () => void shutdown('SIGINT'));

main().catch((error) => {
  console.error(`Spider Chromium startup failed: ${error.message}`);
  process.exit(1);
});
