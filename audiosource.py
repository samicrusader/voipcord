import subprocess
import threading
from sys import stderr

from discord.errors import ClientException
from discord.sinks.core import Sink, default_filters, Filters
from discord.player import FFmpegAudio, _log, CREATE_NO_WINDOW
from discord.oggparse import OggStream
from discord.opus import Encoder as OpusEncoder
from discord.utils import MISSING
from pyVoIP.VoIP import VoIPCall, CallState
from typing import IO, Any


class FFmpegRTPSource(FFmpegAudio):
    """
    Audio source for receiving from PyVoIP VoIPCall objects
    """

    def __init__(self, source: VoIPCall, executable: str = 'ffmpeg'):
        # input opts
        args = ['-loglevel', 'warning', '-probesize', '32', '-analyzeduration', '0', '-fflags', 'nobuffer', '-flags',
                'low_delay', "-f", "u8", "-ar", "8k", "-ac", "1", "-channel_layout", "mono", '-i', 'pipe:']
        # output opts
        args.extend(('-map_metadata', '-1', '-ar', '48k', '-ac', '2', '-channel_layout', 'stereo', '-c:a', 'pcm_s16le'))
        # output stream
        args.extend(('-f', 's16le', '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact', 'pipe:1'))
        subprocess_kwargs = {
            "stdin": subprocess.PIPE,
            "stderr": stderr,
        }
        super().__init__(source, executable=executable, args=args, **subprocess_kwargs)

    def _pipe_writer(self, source: VoIPCall):
        while self._process:
            # read call audio w/ blocking
            if source.state == CallState.ANSWERED:
                data = source.read_audio(160, True)
            else:
                self._stdin.close()
                return
            try:
                self._stdin.write(data)
            except Exception:
                _log.debug(
                    "Write error for %s, this is probably not a problem",
                    self,
                    exc_info=True,
                )
                # at this point the source data is either exhausted or the process is fubar
                self._process.terminate()
                return

    def read(self) -> bytes:
        ret = self._stdout.read(OpusEncoder.FRAME_SIZE)
        if len(ret) != OpusEncoder.FRAME_SIZE:
            return b""
        return ret


class FFmpegRTPSink(Sink):
    def __init__(self, source: VoIPCall, filters=None, executable: str = 'ffmpeg'):
        # input opts
        args = ['-loglevel', 'warning', '-probesize', '32', '-analyzeduration', '0', '-fflags', 'nobuffer', '-flags',
                'low_delay', "-f", "s16le", "-ar", "48k", "-ac", "2", "-channel_layout", "stereo", '-i', 'pipe:']
        # output opts
        args.extend(('-map_metadata', '-1', '-ar', '8k', '-ac', '1', '-channel_layout', 'mono', '-c:a', 'pcm_u8',))
        # output stream
        args.extend(('-f', 'u8', '-fflags', '+bitexact', '-flags:v', '+bitexact', '-flags:a', '+bitexact', 'pipe:1'))
        args = [executable, *args]
        kwargs = {"stdout": subprocess.PIPE, "stdin": subprocess.PIPE, "stderr": stderr}

        self.encoding = "pcm"
        self.vc = None
        self.audio_data = {}

        if filters is None:
            filters = default_filters
        self.filters = filters
        Filters.__init__(self, **self.filters)

        n = f"popen-stdout-writer:{id(self):#x}"
        self._process: subprocess.Popen = self._spawn_process(args, **kwargs)
        self._stdout: IO[bytes] = self._process.stdout  # type: ignore
        self._stdin: IO[bytes] = self._process.stdin
        self._pipe_thread: threading.Thread = threading.Thread(
            target=self._pipe_reader, args=(source,), daemon=True, name=n
        )
        self._pipe_thread.start()

    def _spawn_process(self, args: Any, **subprocess_kwargs: Any) -> subprocess.Popen:
        try:
            process = subprocess.Popen(
                args, creationflags=CREATE_NO_WINDOW, **subprocess_kwargs
            )
        except FileNotFoundError:
            executable = args.partition(" ")[0] if isinstance(args, str) else args[0]
            raise ClientException(f"{executable} was not found.") from None
        except subprocess.SubprocessError as exc:
            raise ClientException(
                f"Popen failed: {exc.__class__.__name__}: {exc}"
            ) from exc
        else:
            return process

    def _kill_process(self) -> None:
        proc = self._process
        if proc is MISSING:
            return

        _log.info("Preparing to terminate ffmpeg process %s.", proc.pid)

        try:
            proc.kill()
        except Exception:
            _log.exception(
                "Ignoring error attempting to kill ffmpeg process %s", proc.pid
            )

        if proc.poll() is None:
            _log.info(
                "ffmpeg process %s has not terminated. Waiting to terminate...",
                proc.pid,
            )
            proc.communicate()
            _log.info(
                "ffmpeg process %s should have terminated with a return code of %s.",
                proc.pid,
                proc.returncode,
            )
        else:
            _log.info(
                "ffmpeg process %s successfully terminated with return code of %s.",
                proc.pid,
                proc.returncode,
            )

    def _pipe_reader(self, source: VoIPCall):
        while self._process:
            try:
                data = self._stdout.read(64000)
                source.write_audio(data)
            except ValueError:
                print('broke')
                _log.debug("Write error for %s", self, exc_info=True)
                return

    def cleanup(self) -> None:
        self._kill_process()
        self._process = self._stdout = self._stdin = MISSING
        self.finished = True

    def format_audio(self, audio):
        return

    def get_all_audio(self):
        """Gets all audio files."""
        return []

    def get_user_audio(self, _):
        """Gets the audio file(s) of one specific user."""
        return ''

    def write(self, data, _):
        if self._process:
            if not data:
                self._stdin.close()
                return
            try:
                self._stdin.write(data)
            except Exception:
                _log.debug(
                    "Write error for %s, this is probably not a problem",
                    self,
                    exc_info=True
                )
                # at this point for source is gone or the process is FUCKED
                self._process.terminate()
                return