# coding: utf-8

import cv2

from .imgutils import crop, _frame_repr, _image_region, pixel_bounding_box
from .logging import ImageLogger
from .types import Region


class FrameDiffer(object):
    """Interface for different algorithms for diffing frames in a sequence.

    Say you have a sequence of frames A, B, C. Typically you will compare frame
    A against B, and then frame B against C. This is a class (not a function)
    so that you can remember work you've done on frame B, so that you don't
    repeat that work when you need to compare against frame C.
    """

    def __init__(self, initial_frame, region=Region.ALL, mask=None,
                 always_compare_to_initial_frame=False):
        self.prev_frame = initial_frame
        self.region = Region.intersect(_image_region(self.prev_frame), region)
        self.mask = mask
        self.always_compare_to_initial_frame = always_compare_to_initial_frame

        if self.mask is not None and mask.shape[:2] != (self.region.height,
                                                        self.region.width):
            raise ValueError(
                "The dimensions of the mask %s don't match the video frame %s" %
                (mask.shape, (region.height, region.width)))

    def diff(self, frame):
        raise NotImplementedError(
            "%s: 'diff' is not implemented" % self.__class__.__name__)


class StrictDiff(FrameDiffer):
    def diff(self, frame):
        f1 = crop(self.prev_frame, self.region)
        f2 = crop(frame, self.region)
        absdiff = cv2.absdiff(f1, f2)
        if self.mask is not None:
            absdiff = cv2.bitwise_and(absdiff, self.mask, absdiff)

        if not self.always_compare_to_initial_frame:
            self.prev_frame = frame

        return absdiff.any()


class MotionDiff(FrameDiffer):
    """The original `wait_for_motion` diff algorithm."""

    def __init__(self, initial_frame, noise_threshold, region=Region.ALL,
                 mask=None):
        super(MotionDiff, self).__init__(initial_frame, region, mask)
        self.noise_threshold = noise_threshold
        self.prev_frame_gray = self.gray(initial_frame)

    def diff(self, frame):
        frame_gray = self.gray(frame)

        imglog = ImageLogger("MotionDiff", region=self.region,
                             noise_threshold=self.noise_threshold)
        imglog.imwrite("source", frame)
        imglog.imwrite("gray", frame_gray)
        imglog.imwrite("previous_frame_gray", self.prev_frame_gray)

        absdiff = cv2.absdiff(self.prev_frame_gray, frame_gray)
        imglog.imwrite("absdiff", absdiff)

        if self.mask is not None:
            absdiff = cv2.bitwise_and(absdiff, self.mask)
            imglog.imwrite("mask", self.mask)
            imglog.imwrite("absdiff_masked", absdiff)

        _, thresholded = cv2.threshold(
            absdiff, int((1 - self.noise_threshold) * 255), 255,
            cv2.THRESH_BINARY)
        eroded = cv2.erode(
            thresholded,
            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
        imglog.imwrite("absdiff_threshold", thresholded)
        imglog.imwrite("absdiff_threshold_erode", eroded)

        if not self.always_compare_to_initial_frame:
            self.prev_frame = frame
            self.prev_frame_gray = frame_gray

        out_region = pixel_bounding_box(eroded)
        if out_region:
            # Undo cv2.erode above:
            out_region = out_region.extend(x=-1, y=-1)
            # Undo crop:
            out_region = out_region.translate(self.region.x, self.region.y)

        motion = bool(out_region)
        result = MotionResult(getattr(frame, "time", None), motion,
                              out_region, frame)
        _log_motion_image_debug(imglog, result)
        return result

    def gray(self, frame):
        return cv2.cvtColor(crop(frame, self.region), cv2.COLOR_BGR2GRAY)


class MotionResult(object):
    """The result from comparing 2 frames with one of the `FrameDiffer`
    algorithms.

    So named for historical reasons.

    :ivar float time: The time at which the video-frame was captured, in
        seconds since 1970-01-01T00:00Z. This timestamp can be compared with
        system time (``time.time()``).

    :ivar bool motion: True if motion was found. This is the same as evaluating
        ``MotionResult`` as a bool. That is, ``if result:`` will behave the
        same as ``if result.motion:``.

    :ivar Region region: Bounding box where the motion was found, or ``None``
        if no motion was found.

    :ivar Frame frame: The video frame in which motion was (or wasn't) found.

    Added in v28: The ``frame`` attribute.
    """
    _fields = ("time", "motion", "region", "frame")

    def __init__(self, time, motion, region, frame):
        self.time = time
        self.motion = motion
        self.region = region
        self.frame = frame

    def __nonzero__(self):
        return self.motion

    def __repr__(self):
        return (
            "MotionResult(time=%s, motion=%r, region=%r, frame=%s)" % (
                "None" if self.time is None else "%.3f" % self.time,
                self.motion, self.region, _frame_repr(self.frame)))


def _log_motion_image_debug(imglog, result):
    if not imglog.enabled:
        return

    template = u"""\
        <h4>
          detect_motion:
          {{ "Found" if result.motion else "Didn't find" }} motion
        </h4>

        {{ annotated_image(result) }}

        <h5>ROI Gray:</h5>
        <img src="gray.png" />

        <h5>Previous frame ROI Gray:</h5>
        <img src="previous_frame_gray.png" />

        <h5>Absolute difference:</h5>
        <img src="absdiff.png" />

        {% if "mask" in images %}
        <h5>Mask:</h5>
        <img src="mask.png" />
        <h5>Absolute difference – masked:</h5>
        <img src="absdiff_masked.png" />
        {% endif %}

        <h5>Threshold (noise_threshold={{noise_threshold}}):</h5>
        <img src="absdiff_threshold.png" />

        <h5>Eroded:</h5>
        <img src="absdiff_threshold_erode.png" />
    """

    imglog.html(template, result=result)
