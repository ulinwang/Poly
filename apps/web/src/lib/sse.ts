import { authorizationHeaders } from './auth';

export interface SseMessage {
  event: string;
  data: string;
}

export async function consumeSse(
  url: string,
  signal: AbortSignal,
  onOpen: () => void,
  onMessage: (message: SseMessage) => void,
): Promise<void> {
  const response = await fetch(url, {
    headers: {
      Accept: 'text/event-stream',
      ...authorizationHeaders(),
    },
    signal,
  });
  if (!response.ok) {
    throw new Error(`SSE request failed with HTTP ${response.status}`);
  }
  if (!response.body) {
    throw new Error('SSE response has no body');
  }

  onOpen();
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  let event = 'message';
  let dataLines: string[] = [];

  const processLine = (rawLine: string) => {
    const line = rawLine.endsWith('\r') ? rawLine.slice(0, -1) : rawLine;
    if (line === '') {
      if (dataLines.length > 0) {
        onMessage({ event, data: dataLines.join('\n') });
      }
      event = 'message';
      dataLines = [];
      return;
    }
    if (line.startsWith(':')) return;

    const separator = line.indexOf(':');
    const field = separator === -1 ? line : line.slice(0, separator);
    let value = separator === -1 ? '' : line.slice(separator + 1);
    if (value.startsWith(' ')) value = value.slice(1);
    if (field === 'event') event = value || 'message';
    if (field === 'data') dataLines.push(value);
  };

  while (!signal.aborted) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done });
    let newline = buffer.indexOf('\n');
    while (newline !== -1) {
      processLine(buffer.slice(0, newline));
      buffer = buffer.slice(newline + 1);
      newline = buffer.indexOf('\n');
    }
    if (done) break;
  }
  if (buffer) processLine(buffer);
  processLine('');
}
