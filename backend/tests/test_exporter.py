import unittest
from pathlib import Path

from backend.app.core.geometry import Box, CropFrame
from backend.app.services.exporter import build_crop_commands, build_ffmpeg_command, build_filter_script


class ExporterTests(unittest.TestCase):
    def test_filter_script_uses_first_crop_and_scales_to_9_16(self):
        frames = [CropFrame(0, Box(100, 100, 120, 320), Box(20, 0, 405, 720), 0.9, False)]
        script = build_filter_script(frames)

        self.assertIn("crop@focus=w=405:h=720:x=20:y=0", script)
        self.assertIn("scale=1080:1920", script)
        self.assertIn("sendcmd", script)

    def test_filter_script_pads_when_crop_extends_beyond_source(self):
        frames = [CropFrame(0, Box(0, 100, 120, 320), Box(-142.5, 0, 405, 720), 0.9, False)]
        script = build_filter_script(frames, frame_width=720, frame_height=720)
        commands = build_crop_commands(frames)

        self.assertIn("pad=w=iw+143:h=ih+0:x=143:y=0:color=black", script)
        self.assertIn("crop@focus=w=405:h=720:x=0:y=0", script)
        self.assertIn("0.000000 focus x 0;", commands)

    def test_command_preserves_audio(self):
        frames = [CropFrame(0, Box(100, 100, 120, 320), Box(20, 0, 405, 720), 0.9, False)]
        command = build_ffmpeg_command(Path("source.mp4"), Path("out.mp4"), frames)

        self.assertIn("-c:a", command)
        self.assertIn("copy", command)
        self.assertEqual(command[-1], "out.mp4")

    def test_crop_commands_include_per_frame_updates(self):
        frames = [
            CropFrame(0, Box(100, 100, 120, 320), Box(20, 0, 405, 720), 0.9, False),
            CropFrame(30, Box(180, 100, 120, 320), Box(80, 0, 405, 720), 0.9, False),
        ]
        commands = build_crop_commands(frames, fps=30)

        self.assertIn("0.000000 focus x 20;", commands)
        self.assertIn("1.000000 focus x 80;", commands)


if __name__ == "__main__":
    unittest.main()
