import unittest

from backend.app.core.geometry import Box, TrackFrame, apply_corrections, build_crop_path, expand_subject_box, fit_aspect_around_box


class GeometryTests(unittest.TestCase):
    def test_crop_box_is_9_16_and_contains_subject(self):
        subject = Box(x=500, y=120, width=120, height=360)
        crop = fit_aspect_around_box(expand_subject_box(subject, 1280, 720), 1280, 720)

        self.assertAlmostEqual(crop.width / crop.height, 9 / 16, places=4)
        self.assertLessEqual(crop.x, subject.x)
        self.assertGreaterEqual(crop.x + crop.width, subject.x + subject.width)
        self.assertLessEqual(crop.y, subject.y)
        self.assertGreaterEqual(crop.y + crop.height, subject.y + subject.height)

    def test_crop_is_clamped_at_frame_edges(self):
        subject = Box(x=0, y=0, width=150, height=400)
        crop = fit_aspect_around_box(expand_subject_box(subject, 1280, 720), 1280, 720)

        self.assertGreaterEqual(crop.x, 0)
        self.assertGreaterEqual(crop.y, 0)
        self.assertLessEqual(crop.x + crop.width, 1280)
        self.assertLessEqual(crop.y + crop.height, 720)

    def test_low_confidence_and_jump_are_suspicious(self):
        track = [
            TrackFrame(0, Box(100, 100, 120, 320), 0.95),
            TrackFrame(1, Box(105, 102, 120, 320), 0.50),
            TrackFrame(2, Box(800, 500, 120, 320), 0.90),
        ]
        crop_path = build_crop_path(track, 1280, 720, smooth_radius=0)

        self.assertFalse(crop_path[0].suspicious)
        self.assertTrue(crop_path[1].suspicious)
        self.assertTrue(crop_path[2].suspicious)

    def test_crop_center_tracks_subject_center_when_not_at_edge(self):
        track = [
            TrackFrame(0, Box(420, 180, 120, 320), 0.95),
            TrackFrame(1, Box(500, 180, 120, 320), 0.95),
            TrackFrame(2, Box(580, 180, 120, 320), 0.95),
        ]
        crop_path = build_crop_path(track, 1280, 720, smooth_radius=0)

        for frame in crop_path:
            self.assertAlmostEqual(frame.crop_box.cx, frame.subject_box.cx, places=4)
            self.assertAlmostEqual(frame.crop_box.cy, frame.subject_box.cy, places=4)

    def test_crop_center_stays_on_subject_when_subject_near_edge(self):
        track = [TrackFrame(0, Box(0, 180, 120, 320), 0.95)]
        crop = build_crop_path(track, 1280, 720, smooth_radius=0)[0].crop_box

        self.assertGreaterEqual(crop.x, 0)
        self.assertLessEqual(crop.x + crop.width, 1280)
        self.assertLessEqual(crop.y + crop.height, 720)

    def test_corrections_replace_only_target_frames_and_interpolate_gaps(self):
        track = [
            TrackFrame(0, Box(100, 100, 120, 320), 0.80),
            TrackFrame(1, Box(110, 100, 120, 320), 0.40),
            TrackFrame(2, Box(120, 100, 120, 320), 0.40),
            TrackFrame(3, Box(400, 100, 120, 320), 0.80),
        ]
        corrected = apply_corrections(track, {0: Box(100, 100, 120, 320), 3: Box(400, 100, 120, 320)})

        self.assertEqual(corrected[0].subject_box.x, 100)
        self.assertAlmostEqual(corrected[1].subject_box.x, 200)
        self.assertAlmostEqual(corrected[2].subject_box.x, 300)
        self.assertEqual(corrected[3].subject_box.x, 400)
        self.assertGreaterEqual(corrected[1].confidence, 0.92)


if __name__ == "__main__":
    unittest.main()
