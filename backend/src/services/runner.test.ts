import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { EventEmitter } from 'events';
import { spawnRun, createRunHandle } from './runner';

const mockSpawn = vi.fn();

vi.mock('child_process', async (importOriginal) => {
  const mod = await importOriginal<typeof import('child_process')>();
  return {
    ...mod,
    spawn: (...args: Parameters<typeof mod.spawn>) => mockSpawn(...args),
  };
});

describe('spawnRun', () => {
  let mockChild: EventEmitter & {
    stdin: EventEmitter & { write: ReturnType<typeof vi.fn>; end: ReturnType<typeof vi.fn> };
    stdout: EventEmitter & { setEncoding: ReturnType<typeof vi.fn> };
    stderr: EventEmitter & { setEncoding: ReturnType<typeof vi.fn> };
    kill: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    vi.clearAllMocks();
    mockChild = Object.assign(new EventEmitter(), {
      stdin: Object.assign(new EventEmitter(), {
        write: vi.fn(),
        end: vi.fn(),
      }),
      stdout: Object.assign(new EventEmitter(), {
        setEncoding: vi.fn(),
      }),
      stderr: Object.assign(new EventEmitter(), {
        setEncoding: vi.fn(),
      }),
      kill: vi.fn(),
    });
    mockSpawn.mockReturnValue(mockChild);
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it('spawns the Python CLI wrapper with correct args and cwd', () => {
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, vi.fn());

    expect(mockSpawn).toHaveBeenCalledWith('.venv/bin/python3', ['webapp/runner_cli.py'], {
      cwd: '/Users/moonshot/Projects/Poly/polymetl',
    });
  });

  it('writes config JSON to stdin', () => {
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, vi.fn());

    expect(mockChild.stdin.write).toHaveBeenCalledTimes(1);
    const config = JSON.parse(mockChild.stdin.write.mock.calls[0][0] as string);
    expect(config).toMatchObject({
      slug: 'slug1',
      n_agents: 4,
      n_ticks: 10,
      persona_set: 'archetype',
      seed: 0,
      temperature: 0.0,
      data_dir: 'data',
    });
    expect(mockChild.stdin.end).toHaveBeenCalled();
  });

  it('parses stdout JSON lines and calls onEvent', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.stdout.emit('data', '{"kind": "tick_started", "data": {"tick":1}}\n');
    expect(onEvent).toHaveBeenCalledWith('tick_started', { tick: 1 });
  });

  it('buffers partial lines across stdout chunks', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.stdout.emit('data', '{"kind": "tick_started", "data": {"tick":1}}\n{"kind": "agent_de');
    mockChild.stdout.emit('data', 'cision", "data": {"agent_id": 2}}\n');

    expect(onEvent).toHaveBeenCalledTimes(2);
    expect(onEvent).toHaveBeenNthCalledWith(1, 'tick_started', { tick: 1 });
    expect(onEvent).toHaveBeenNthCalledWith(2, 'agent_decision', { agent_id: 2 });
  });

  it('sets finished=true on __end__', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.stdout.emit('data', '{"kind": "__end__", "data": {}}\n');
    expect(handle.finished).toBe(true);
    expect(onEvent).toHaveBeenCalledWith('__end__', {});
  });

  it('sends SIGTERM when handle.cancel is set', () => {
    vi.useFakeTimers();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, vi.fn());

    handle.cancel = true;
    vi.advanceTimersByTime(300);
    expect(mockChild.kill).toHaveBeenCalledWith('SIGTERM');
  });

  it('emits error and __end__ on non-zero exit before __end__', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.emit('exit', 1);
    expect(onEvent).toHaveBeenCalledWith(
      'error',
      expect.objectContaining({ message: expect.stringContaining('1') }),
    );
    expect(onEvent).toHaveBeenCalledWith('__end__', {});
    expect(handle.finished).toBe(true);
  });

  it('does not duplicate __end__ when exit follows a prior __end__', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.stdout.emit('data', '{"kind": "__end__", "data": {}}\n');
    onEvent.mockClear();
    mockChild.emit('exit', 0);
    expect(onEvent).not.toHaveBeenCalled();
  });

  it('emits error and __end__ on process error event', () => {
    const onEvent = vi.fn();
    const handle = createRunHandle('r1', 'slug1', 4, 10, 'archetype');
    spawnRun(handle, onEvent);

    mockChild.emit('error', new Error('spawn failed'));
    expect(onEvent).toHaveBeenCalledWith(
      'error',
      expect.objectContaining({ message: 'spawn failed' }),
    );
    expect(onEvent).toHaveBeenCalledWith('__end__', {});
    expect(handle.finished).toBe(true);
  });
});
