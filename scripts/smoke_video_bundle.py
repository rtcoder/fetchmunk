"""Exercise frozen yt-dlp, bundled Deno and FFmpeg against localhost DASH media."""

import argparse
from functools import partial
import http.server
import json
from pathlib import Path
import queue
import re
import subprocess
import tempfile
import threading


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


def check(backend):
    exe = backend / 'Contents/MacOS/fetchmunk-backend'
    runtime = backend / 'Contents/Frameworks'
    deno = runtime / 'deno-bin/deno'
    ffmpegs = list((runtime / 'imageio_ffmpeg/binaries').glob('ffmpeg-*'))
    assert exe.is_file() and deno.is_file(), 'Missing bundled worker or Deno'
    assert len(ffmpegs) == 1 and ffmpegs[0].is_file(), 'Missing bundled FFmpeg'
    ffmpeg = ffmpegs[0]
    with tempfile.TemporaryDirectory(prefix='Fetchmunk video smoke ż ') as tmp:
        root = Path(tmp)
        # No PATH discovery, user configuration, or external Python environment.
        env = {'PATH': '', 'HOME': tmp, 'TMPDIR': tmp}
        deno_version = subprocess.run(
            [str(deno), '--version'], check=True, capture_output=True,
            text=True, env=env, cwd=root, timeout=15,
        ).stdout.splitlines()[0]
        assert deno_version.startswith('deno '), 'Bundled Deno did not start'
        subprocess.run([
            str(ffmpeg), '-v', 'error', '-f', 'lavfi', '-i',
            'color=size=64x64:rate=5:duration=1', '-f', 'lavfi', '-i',
            'anullsrc=r=8000:cl=mono', '-map', '0:v', '-map', '0:v',
            '-map', '1:a', '-filter:v:0', 'scale=32:32',
            '-filter:v:1', 'scale=64:64', '-c:v', 'libx264',
            '-b:v:0', '10k', '-b:v:1', '50k', '-c:a', 'aac',
            '-t', '1', '-f', 'dash', '-adaptation_sets',
            'id=0,streams=v id=1,streams=a', str(root / 'fixture.mpd'),
        ], check=True, capture_output=True, env=env, cwd=root, timeout=30)

        server = http.server.ThreadingHTTPServer(
            ('127.0.0.1', 0), partial(Handler, directory=tmp),
        )
        server_thread = threading.Thread(target=server.serve_forever, daemon=True)
        server_thread.start()
        process = None
        try:
            process = subprocess.Popen(
                [str(exe), '--worker'], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, env=env, cwd=root,
            )
            messages = queue.Queue()

            def reader():
                try:
                    for line in process.stdout:
                        messages.put(json.loads(line))
                except Exception as exc:
                    messages.put(exc)
                finally:
                    messages.put(None)

            thread = threading.Thread(target=reader, daemon=True)
            thread.start()
            output = root / 'output $HOME % ż'
            process.stdin.write(json.dumps({
                'job_id': 'video-bundle-smoke', 'attempt': 1,
                'url': f'http://127.0.0.1:{server.server_port}/fixture.mpd',
                'output_dir': str(output), 'archive_path': str(root / 'archive.sqlite'),
                'engine': 'yt-dlp',
            }) + '\n')
            process.stdin.flush()
            # Keep stdin open: EOF deliberately terminates orphaned workers.
            events = []
            while True:
                message = messages.get(timeout=60)
                assert isinstance(message, dict), 'Worker stopped or emitted invalid JSON'
                if message['kind'] == 'result':
                    result = message['data']
                    break
                events.append(message)
            process.wait(timeout=10)
            assert process.returncode == 0, 'Frozen worker exited unsuccessfully'
            assert not process.stderr.read(), 'Frozen worker leaked diagnostic output'
            assert result['error_code'] is None and result['downloaded'] == 1, result
            formats = [f for event in events if event['kind'] == 'video.formats' for f in event['data']['formats']]
            assert {32, 64}.issubset({f['height'] for f in formats}), 'DASH quality discovery failed'
            media = list(output.glob('*.mp4'))
            assert len(media) == 1 and media[0].stem.isdecimal(), 'Unexpected final output'
            probe = subprocess.run(
                [str(ffmpeg), '-i', str(media[0]), '-f', 'null', '-'],
                capture_output=True, text=True, env=env, cwd=root, timeout=30,
            )
            assert probe.returncode == 0, 'Merged media cannot be decoded'
            assert re.search(r'Video:.*\b64x64\b', probe.stderr), 'Highest video quality was not selected'
            assert 'Audio:' in probe.stderr, 'Merged output has no audio stream'
            assert len([p for p in output.iterdir() if p.is_file()]) == 1, 'Unmerged streams remain'
            print(json.dumps({
                'result': 'PASS', 'frozen_worker': 'PASS', 'deno': deno_version,
                'quality_discovery': 'PASS', 'best_video_and_audio_merge': 'PASS',
                'isolation': 'empty PATH; temporary HOME/cwd; localhost fixtures only',
            }, indent=2))
        finally:
            if process is not None:
                if process.poll() is None:
                    process.kill()
                    process.wait()
                for stream in (process.stdin, process.stdout, process.stderr):
                    stream.close()
            server.shutdown()
            server.server_close()
            server_thread.join()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    target = parser.add_mutually_exclusive_group(required=True)
    target.add_argument('--app', type=Path)
    target.add_argument('--backend', type=Path, help='Standalone frozen helper for local diagnostics')
    args = parser.parse_args()
    backend = args.backend or args.app / 'Contents/Helpers/FetchmunkBackend.app'
    check(backend.resolve())
