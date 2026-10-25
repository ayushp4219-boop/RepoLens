#!/usr/bin/env node
/**
 * Generates simple placeholder PNG icons for RepoLens.
 * Uses raw PNG byte construction - no dependencies needed.
 */
import { createWriteStream } from 'fs';
import { createHash } from 'crypto';
import { deflateSync } from 'zlib';

function createPng(size, r, g, b) {
  const width = size;
  const height = size;

  // PNG signature
  const signature = Buffer.from([137, 80, 78, 71, 13, 10, 26, 10]);

  function chunk(type, data) {
    const typeBuffer = Buffer.from(type, 'ascii');
    const length = Buffer.alloc(4);
    length.writeUInt32BE(data.length, 0);
    const crcData = Buffer.concat([typeBuffer, data]);
    const crc = crc32(crcData);
    const crcBuffer = Buffer.alloc(4);
    crcBuffer.writeUInt32BE(crc, 0);
    return Buffer.concat([length, typeBuffer, data, crcBuffer]);
  }

  function crc32(buf) {
    let crc = 0xffffffff;
    for (const byte of buf) {
      crc ^= byte;
      for (let i = 0; i < 8; i++) {
        crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0);
      }
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  // IHDR
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;  // bit depth
  ihdr[9] = 2;  // color type RGB
  ihdr[10] = 0; // compression
  ihdr[11] = 0; // filter
  ihdr[12] = 0; // interlace

  // Image data (raw scanlines with filter byte)
  const rawData = [];
  for (let y = 0; y < height; y++) {
    rawData.push(0); // filter byte: None
    for (let x = 0; x < width; x++) {
      // Draw a simple icon: dark bg with accent circle
      const cx = width / 2;
      const cy = height / 2;
      const dist = Math.sqrt((x - cx) ** 2 + (y - cy) ** 2);
      const radius = width * 0.35;

      if (dist <= radius) {
        rawData.push(r, g, b); // accent color
      } else {
        rawData.push(13, 17, 23); // dark bg #0d1117
      }
    }
  }

  const compressed = deflateSync(Buffer.from(rawData));
  const idat = chunk('IDAT', compressed);
  const iend = chunk('IEND', Buffer.alloc(0));

  return Buffer.concat([signature, chunk('IHDR', ihdr), idat, iend]);
}

const sizes = [16, 32, 48, 128];
for (const size of sizes) {
  const png = createPng(size, 88, 166, 255); // #58a6ff
  const stream = createWriteStream(`public/icons/icon${size}.png`);
  stream.write(png);
  stream.end();
  console.log(`Created icon${size}.png`);
}
