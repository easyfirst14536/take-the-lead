const express = require('express');
const cors = require('cors');
const dotenv = require('dotenv');
const path = require('path');
const fetch = require('node-fetch');

dotenv.config();

const app = express();
const PORT = process.env.PORT || 4000;
const COZE_API_KEY = process.env.COZE_API_KEY;
const COZE_BOT_ID = process.env.COZE_BOT_ID;
const COZE_API_BASE_URL = (process.env.COZE_API_BASE_URL || 'https://api.coze.cn').replace(/\/$/, '');
const COZE_CHAT_URL = `${COZE_API_BASE_URL}/open_api/v2/chat`;

app.use(express.json({ limit: '1mb' }));
app.use(cors());
app.use(express.static(path.join(__dirname, '../frontend')));

function writeSse(res, event, payload) {
  res.write(`event: ${event}\n`);
  res.write(`data: ${JSON.stringify(payload)}\n\n`);
}

function fallbackMarkdown() {
  return `| Field | Value | Status |
| --- | --- | --- |
| AI output | No valid content was parsed from the Coze stream | Check backend logs for raw Coze chunks |
| Next step | Verify COZE_API_BASE_URL, COZE_API_KEY, and COZE_BOT_ID | Pending |`;
}

function maskSecret(value) {
  if (!value) return '(empty)';
  if (value.length <= 12) return `${value.slice(0, 3)}***`;
  return `${value.slice(0, 8)}...${value.slice(-4)}`;
}

function isAnswerLike(value) {
  if (!value || typeof value !== 'object') return false;

  const type = String(value.type || value.message_type || value.role || '').toLowerCase();
  const event = String(value.event || '').toLowerCase();

  return (
    type === 'answer' ||
    type === 'assistant' ||
    event.includes('answer') ||
    event.includes('message.delta') ||
    event.includes('message.completed')
  );
}

function pickString(...values) {
  return values.find((value) => typeof value === 'string' && value.length > 0) || '';
}

function extractMessageContent(message) {
  if (!message || typeof message !== 'object') return '';

  if (isAnswerLike(message)) {
    const direct = pickString(message.content, message.text, message.answer, message.output);
    if (direct) return direct;
  }

  if (Array.isArray(message.content)) {
    return message.content
      .map((item) => {
        if (typeof item === 'string') return item;
        return pickString(item?.text, item?.content, item?.value);
      })
      .join('');
  }

  return '';
}

function extractCozeContent(payload) {
  if (!payload || typeof payload !== 'object') return '';

  const candidates = [];

  if (isAnswerLike(payload)) {
    candidates.push(pickString(payload.content, payload.text, payload.answer, payload.output));
  }

  candidates.push(extractMessageContent(payload.message));
  candidates.push(extractMessageContent(payload.data));
  candidates.push(extractMessageContent(payload.data?.message));

  if (Array.isArray(payload.messages)) {
    candidates.push(payload.messages.map(extractMessageContent).join(''));
  }

  if (Array.isArray(payload.data?.messages)) {
    candidates.push(payload.data.messages.map(extractMessageContent).join(''));
  }

  if (Array.isArray(payload.choices)) {
    candidates.push(
      payload.choices
        .map((choice) => {
          return pickString(
            choice.delta?.content,
            choice.delta?.text,
            choice.message?.content,
            choice.message?.text,
            choice.content,
            choice.text
          );
        })
        .join('')
    );
  }

  if (payload.content && typeof payload.content === 'string' && !payload.type) {
    candidates.push(payload.content);
  }

  return candidates.find((content) => typeof content === 'string' && content.length > 0) || '';
}

function parseCozeSseBuffer(buffer, onPayload) {
  const lines = buffer.split(/\r?\n/);
  const rest = lines.pop() || '';

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith(':')) continue;
    if (!trimmed.startsWith('data:')) continue;

    const jsonText = trimmed.slice(5).trim();
    if (!jsonText || jsonText === '[DONE]') continue;

    try {
      onPayload(JSON.parse(jsonText));
    } catch (error) {
      console.error('[Coze] Failed to parse JSON:', error.message);
      console.error('[Coze] Unparsed data line:', jsonText);
    }
  }

  return rest;
}

function readCozeStreamWithEvents(cozeResponse, onPayload) {
  return new Promise((resolve, reject) => {
    let buffer = '';

    cozeResponse.body.on('data', (chunk) => {
      const rawChunk = chunk.toString('utf8');
      console.log('[Coze raw chunk]');
      console.log(rawChunk);

      buffer += rawChunk;
      buffer = parseCozeSseBuffer(buffer, onPayload);
    });

    cozeResponse.body.on('end', () => {
      if (buffer.trim()) {
        buffer = parseCozeSseBuffer(`${buffer}\n`, onPayload);
      }
      resolve();
    });

    cozeResponse.body.on('error', reject);
  });
}

app.post('/api/shred', async (req, res) => {
  const rawText = req.body?.text;

  if (!COZE_API_KEY || !COZE_BOT_ID) {
    return res.status(500).json({
      error: 'Missing COZE_API_KEY or COZE_BOT_ID. Check backend/.env.',
    });
  }

  if (!rawText || typeof rawText !== 'string') {
    return res.status(400).json({
      error: 'Request body must include a non-empty string field named "text".',
    });
  }

  res.writeHead(200, {
    'Content-Type': 'text/event-stream; charset=utf-8',
    'Cache-Control': 'no-cache, no-transform',
    Connection: 'keep-alive',
    'Access-Control-Allow-Origin': '*',
  });

  const cozePrompt = `Please convert the following messy office text into a clean Markdown table.

Rules:
1. Output only a valid Markdown table.
2. The first row must be the header.
3. The second row must be the separator row.
4. Do not add explanation before or after the table.
5. Use Chinese column names when the input is Chinese.

Input:
${rawText.trim()}`;

  let accumulatedMarkdown = '';

  try {
    console.log('[Coze] request start');
    console.log('[Coze] chat_url:', COZE_CHAT_URL);
    console.log('[Coze] bot_id:', COZE_BOT_ID);
    console.log('[Coze] api_key:', maskSecret(COZE_API_KEY));
    console.log('[Coze] query length:', cozePrompt.length);

    const cozeResponse = await fetch(COZE_CHAT_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${COZE_API_KEY}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        bot_id: COZE_BOT_ID,
        user: 'office-clerk',
        query: cozePrompt,
        stream: true,
      }),
    });

    console.log('[Coze] status:', cozeResponse.status);
    console.log('[Coze] headers:', Object.fromEntries(cozeResponse.headers.entries()));

    if (!cozeResponse.ok) {
      const detail = await cozeResponse.text();
      console.error('[Coze] API error detail:', detail);
      writeSse(res, 'error', { message: 'Coze API returned an error.', detail });
      return res.end();
    }

    await readCozeStreamWithEvents(cozeResponse, (payload) => {
      console.log('[Coze parsed payload]', JSON.stringify(payload, null, 2));

      const part = extractCozeContent(payload);
      if (!part) {
        console.log('[Coze] No answer content found in this payload.');
        return;
      }

      accumulatedMarkdown += part;
      writeSse(res, 'progress', { markdown: accumulatedMarkdown });
    });

    if (!accumulatedMarkdown.trim()) {
      console.warn('[Coze] No valid Markdown parsed. Sending fallback table.');
      accumulatedMarkdown = fallbackMarkdown();
    }

    writeSse(res, 'done', { markdown: accumulatedMarkdown });
    res.end();
  } catch (error) {
    console.error('[Coze] Request or stream failed:', error);

    const markdown = accumulatedMarkdown.trim() ? accumulatedMarkdown : fallbackMarkdown();
    writeSse(res, 'progress', { markdown });
    writeSse(res, 'done', { markdown });
    res.end();
  }
});

app.options('/api/shred', cors());

app.post('/api/test', (req, res) => {
  res.json({
    markdown: `| Name | Phone | Department |
| --- | --- | --- |
| Zhang San | 13800000000 | Admin |
| Li Si | 13900000000 | Finance |`,
  });
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, '../frontend/index.html'));
});

app.listen(PORT, () => {
  console.log(`SmartOffice AI backend listening on http://localhost:${PORT}`);
});
