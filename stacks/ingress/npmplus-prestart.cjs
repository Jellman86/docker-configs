'use strict';
// Runs as root before NPMplus's own entrypoint, on every container start.
// 1. Remove the image's default X-Forwarded-For trust of every private range.
//    Any LAN client or the Docker gateway could otherwise spoof its address.
//    Only loopback/unix remain globally trusted; tunnel hosts opt in per host
//    with set_real_ip_from for the fixed cloudflared address.
// 2. Provision the CrowdSec bouncer from Dockhand's encrypted variable. Never
//    log the key or put it in an argument. Stream mode, AppSec off.
const fs = require('node:fs');
const path = require('node:path');

const NGINX = process.env.NPMPLUS_NGINX_CONF || '/usr/local/nginx/conf/nginx.conf';
const BROAD = ['10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16', '169.254.0.0/16', 'fc00::/7', 'fec0::/10'];
let conf = fs.readFileSync(NGINX, 'utf8');
for (const range of BROAD) {
  conf = conf.split('\n').filter((line) => line.trim() !== `set_real_ip_from ${range};`).join('\n');
}
for (const range of BROAD) {
  if (conf.includes(`set_real_ip_from ${range}`)) throw new Error(`Broad real IP trust remains: ${range}`);
}
fs.writeFileSync(NGINX, conf);

const key = process.env.CROWDSEC_BOUNCER_KEY;
if (!key || !/^[A-Za-z0-9_-]{32,}$/.test(key)) {
  throw new Error('A valid Dockhand-managed CrowdSec bouncer key is required');
}
const data = process.env.NPMPLUS_DATA_DIR || '/data';
const directory = path.join(data, 'crowdsec');
fs.mkdirSync(directory, {recursive: true, mode: 0o700});
if (fs.lstatSync(directory).isSymbolicLink()) {
  throw new Error('Bouncer configuration must use its real application directory');
}
const file = path.join(directory, 'crowdsec.conf');
const example = process.env.NPMPLUS_CROWDSEC_EXAMPLE || '/etc/crowdsec.conf.example';
let text = fs.existsSync(file) ? fs.readFileSync(file, 'utf8') : fs.readFileSync(example, 'utf8');
const values = {ENABLED: 'true', API_URL: 'http://crowdsec:8080', API_KEY: key,
  MODE: 'stream', UPDATE_FREQUENCY: '10', APPSEC_URL: '',
  APPSEC_FAILURE_ACTION: 'passthrough', ALWAYS_SEND_TO_APPSEC: 'false', SSL_VERIFY: 'true'};
for (const [name, value] of Object.entries(values)) {
  const line = name + '=' + value;
  const expression = new RegExp('^' + name + '=.*$', 'm');
  text = expression.test(text) ? text.replace(expression, () => line) : text + '\n' + line;
}
const temporary = path.join(directory, '.crowdsec.conf.provisioning');
fs.rmSync(temporary, {force: true});
const fd = fs.openSync(temporary,
  fs.constants.O_WRONLY | fs.constants.O_CREAT | fs.constants.O_EXCL | fs.constants.O_NOFOLLOW, 0o600);
try { fs.writeFileSync(fd, text); fs.fchmodSync(fd, 0o600); }
finally { fs.closeSync(fd); }
fs.renameSync(temporary, file);
const uid = Number(process.env.PUID || 1000);
const gid = Number(process.env.PGID || 1000);
fs.chownSync(directory, uid, gid);
fs.chownSync(file, uid, gid);
fs.chmodSync(file, 0o600);
console.log('NPMplus prestart: private real IP trust removed; CrowdSec bouncer provisioned');
