"""
GooferVideoConcat – Concatenate up to 6 VIDEO clips into one.

Self-contained video stitching node for ComfyUI-Goofer.
Upscaler with auto-download: Real-ESRGAN (primary), nvvfx RTX VSR (if installed), bicubic (fallback).
Crossfade dissolve transitions between clips (configurable overlap).

The VIDEO type is a VideoFromComponents object from comfy_api with methods:
  - get_components() → (images, audio, ...)
  - get_frame_rate() → float
  - get_frame_count() → int
  - get_dimensions() → (w, h)
  - get_duration() → float

Author: Jeffrey A. Brick
License: MIT
"""

from __future__ import annotations

import logging
import torch

logger = logging.getLogger("goofer.video_concat")

REQUIRED_KEYS = {"images", "audio", "fps"}


# ---------------------------------------------------------------------------
# Extract components from a VideoFromComponents object
# ---------------------------------------------------------------------------

def _extract_components(video_obj):
    """Pull (images_tensor, audio_obj, fps) from a VIDEO / VideoFromComponents."""
    fps = 30.0

    if hasattr(video_obj, "get_components"):
        components = video_obj.get_components()
        images = None
        audio = None

        if isinstance(components, dict):
            images = components.get("images")
            if images is None:
                images = components.get("frames")
            audio = components.get("audio")
            fps = float(components.get("fps", fps))
        elif isinstance(components, (tuple, list)):
            if len(components) >= 1:
                images = components[0]
            if len(components) >= 2:
                audio = components[1]
            if len(components) >= 3 and isinstance(components[2], (int, float)):
                fps = float(components[2])
        else:
            images = getattr(components, "images", None)
            if images is None:
                images = getattr(components, "frames", None)
            audio = getattr(components, "audio", None)
            fps_val = getattr(components, "fps", None)
            if fps_val is not None:
                fps = float(fps_val)

        if hasattr(video_obj, "get_frame_rate"):
            try:
                fr = video_obj.get_frame_rate()
                if fr and fr > 0:
                    fps = float(fr)
            except Exception:
                pass

        if images is not None:
            return images, audio, fps

    for img_attr in ("images", "frames", "samples", "video_frames"):
        if hasattr(video_obj, img_attr):
            val = getattr(video_obj, img_attr)
            if val is not None and isinstance(val, torch.Tensor):
                audio = getattr(video_obj, "audio", None)
                if hasattr(video_obj, "get_frame_rate"):
                    try:
                        fps = float(video_obj.get_frame_rate())
                    except Exception:
                        pass
                return val, audio, fps

    if isinstance(video_obj, dict):
        images = video_obj.get("images")
        if images is None:
            images = video_obj.get("frames")
        audio = video_obj.get("audio")
        fps = float(video_obj.get("fps", 30.0))
        if images is not None:
            return images, audio, fps

    attrs = [a for a in dir(video_obj) if not a.startswith("_")]
    raise TypeError(
        f"GooferVideoConcat: cannot extract frames from {type(video_obj).__name__}. "
        f"Available methods: {attrs}"
    )


# ---------------------------------------------------------------------------
# Lightweight VIDEO-compatible wrapper
# ---------------------------------------------------------------------------

class _GooferConcatVideo:
    """VIDEO-compatible object that satisfies SaveVideo's interface."""

    def __init__(self, images, audio, fps):
        self._images = images
        self._audio = audio
        self._fps = float(fps)

    def get_components(self):
        return {
            "images": self._images,
            "audio": self._audio,
            "fps": self._fps,
        }

    def get_dimensions(self):
        return (int(self._images.shape[2]), int(self._images.shape[1]))

    def get_frame_rate(self):
        return self._fps

    def get_frame_count(self):
        return int(self._images.shape[0])

    def get_duration(self):
        return self._images.shape[0] / self._fps

    def get_stream_source(self):
        return None

    def get_container_format(self):
        return None

    def as_trimmed(self):
        return self

    def save_to(self, path, **kwargs):
        """Fallback save via PyAV — muxes video + audio."""
        import av
        container = None
        try:
            container = av.open(str(path), mode='w')
            w, h = self.get_dimensions()

            from fractions import Fraction
            fps_frac = Fraction(self._fps).limit_denominator(10000)
            video_stream = container.add_stream('h264', rate=fps_frac)
            video_stream.width = w
            video_stream.height = h
            video_stream.pix_fmt = 'yuv420p'

            audio_stream = None
            wf_np = None
            sample_rate = 44100
            if self._audio is not None:
                try:
                    waveform = self._audio.get("waveform") if isinstance(self._audio, dict) else self._audio
                    sample_rate = int(self._audio.get("sample_rate", 44100)) if isinstance(self._audio, dict) else 44100
                    if waveform is not None:
                        wf = waveform.cpu().float()
                        if wf.dim() == 3:
                            wf = wf.squeeze(0)
                        if wf.dim() == 1:
                            wf = wf.unsqueeze(0)
                        wf_np = wf.numpy()
                        n_channels = wf_np.shape[0]
                        layout_str = 'stereo' if n_channels >= 2 else 'mono'
                        if n_channels >= 2:
                            wf_np = wf_np[:2]
                        audio_stream = container.add_stream('aac', rate=sample_rate)
                        try:
                            audio_stream.layout = av.AudioLayout(layout_str)
                        except (TypeError, AttributeError):
                            audio_stream.layout = layout_str
                except Exception as ae:
                    logger.warning("_GooferConcatVideo: audio setup failed: %s", ae)
                    audio_stream = None
                    wf_np = None

            for i in range(self._images.shape[0]):
                frame_data = (self._images[i].cpu().numpy() * 255).clip(0, 255).astype('uint8')
                frame = av.VideoFrame.from_ndarray(frame_data, format='rgb24')
                for packet in video_stream.encode(frame):
                    container.mux(packet)
            for packet in video_stream.encode():
                container.mux(packet)

            if audio_stream is not None and wf_np is not None:
                try:
                    frame_size = audio_stream.codec_context.frame_size or 1024
                    total_samples = wf_np.shape[-1]
                    pts = 0
                    for start in range(0, total_samples, frame_size):
                        chunk = wf_np[:, start:start + frame_size]
                        audio_frame = av.AudioFrame.from_ndarray(chunk, format='fltp',
                                                                  layout=audio_stream.layout)
                        audio_frame.sample_rate = sample_rate
                        audio_frame.pts = pts
                        pts += chunk.shape[-1]
                        for packet in audio_stream.encode(audio_frame):
                            container.mux(packet)
                    for packet in audio_stream.encode():
                        container.mux(packet)
                except Exception as ae:
                    logger.warning("_GooferConcatVideo: audio encoding failed: %s", ae)

            container.close()
            container = None
        except Exception as e:
            if container is not None:
                try:
                    container.close()
                except Exception:
                    pass
            raise


def _build_video(images, audio, fps):
    """Reconstruct a VIDEO-compatible object from concatenated components."""
    try:
        from comfy_api.latest._input_impl.video_types import VideoFromComponents as VFC
        vid = VFC(images=images, audio=audio, fps=fps)
        if hasattr(vid, 'get_dimensions'):
            return vid
    except Exception:
        pass
    return _GooferConcatVideo(images, audio, fps)


# ---------------------------------------------------------------------------
# RTX Video Super Resolution
# ---------------------------------------------------------------------------

def _upscale(images, target_resolution=1080, quality="ULTRA"):
    """Upscale frame tensor. Tries Real-ESRGAN (auto-downloads), then nvvfx, then bicubic.

    Real-ESRGAN: pip install realesrgan — model weights auto-download on first run.
    nvvfx: Only if NVIDIA VFX SDK is manually installed (optional, faster on RTX GPUs).
    Bicubic: Always available as a last resort (torch-native, no extra deps).
    """
    import time
    import numpy as np

    n_frames, h, w, c = images.shape
    scale = target_resolution / h
    target_w = max(8, round((w * scale) / 8) * 8)
    target_h = max(8, round(target_resolution / 8) * 8)

    if scale <= 1.0:
        logger.info("Upscale skipped — target %dp is not larger than source %dp", target_resolution, h)
        return images

    t0 = time.time()

    # --- Strategy 1: Real-ESRGAN (auto-downloads model weights) ---
    try:
        # torchvision >= 0.16 removed functional_tensor; patch it before basicsr imports it
        import sys as _sys
        import torchvision.transforms.functional as _tvtf
        if "torchvision.transforms.functional_tensor" not in _sys.modules:
            _sys.modules["torchvision.transforms.functional_tensor"] = _tvtf

        from realesrgan import RealESRGANer
        from basicsr.archs.rrdbnet_arch import RRDBNet

        logger.info("Real-ESRGAN: %dx%d -> %dx%d (quality=%s) -- %d frames",
                    w, h, target_w, target_h, quality, n_frames)

        # RealESRGAN_x4plus — auto-downloads ~64MB model from GitHub releases
        model = RRDBNet(num_in_ch=3, num_out_ch=3, num_feat=64,
                        num_block=23, num_grow_ch=32, scale=4)

        tile_sizes = {"LOW": 256, "MEDIUM": 384, "HIGH": 512, "ULTRA": 640}
        tile = tile_sizes.get(quality, 512)

        upsampler = RealESRGANer(
            scale=4,
            model_path="https://github.com/xinntao/Real-ESRGAN/releases/download/v0.1.0/RealESRGAN_x4plus.pth",
            model=model,
            tile=tile,
            tile_pad=10,
            pre_pad=0,
            half=torch.cuda.is_available(),
        )

        upscaled_frames = []
        for i in range(n_frames):
            # float [0,1] RGB NHWC -> uint8 BGR for ESRGAN
            frame = (images[i].cpu().numpy() * 255).clip(0, 255).astype(np.uint8)
            frame_bgr = frame[:, :, ::-1].copy()

            output_bgr, _ = upsampler.enhance(frame_bgr, outscale=scale)

            # uint8 BGR -> float [0,1] RGB
            output_rgb = output_bgr[:, :, ::-1].copy().astype(np.float32) / 255.0
            upscaled_frames.append(torch.from_numpy(output_rgb))

            if (i + 1) % 20 == 0 or i == n_frames - 1:
                logger.info("  Real-ESRGAN progress: %d/%d frames", i + 1, n_frames)

        # Cleanup ESRGAN model from VRAM
        del upsampler
        torch.cuda.empty_cache()

        result = torch.stack(upscaled_frames, dim=0)

        # Real-ESRGAN outscale can produce approximate dimensions;
        # resize to exact target so output matches nvvfx/bicubic paths.
        if result.shape[1] != target_h or result.shape[2] != target_w:
            logger.info("Real-ESRGAN: resizing %dx%d -> exact %dx%d",
                        result.shape[2], result.shape[1], target_w, target_h)
            result = torch.nn.functional.interpolate(
                result.permute(0, 3, 1, 2),
                size=(target_h, target_w),
                mode="bicubic", align_corners=False,
            ).clamp(0, 1).permute(0, 2, 3, 1)

        elapsed = time.time() - t0
        logger.info("Real-ESRGAN done in %.1fs (%.2f fps, %d frames -> %dx%d)",
                    elapsed, n_frames / elapsed if elapsed > 0 else 0,
                    n_frames, result.shape[2], result.shape[1])
        return result

    except ImportError:
        logger.info("Real-ESRGAN not installed (pip install realesrgan). Trying fallbacks...")
    except Exception as e:
        logger.warning("Real-ESRGAN failed: %s. Trying fallbacks...", e)

    # --- Strategy 2: nvvfx (NVIDIA VFX SDK, if manually installed) ---
    try:
        import nvvfx

        logger.info("nvvfx RTX VSR: %dx%d -> %dx%d (quality=%s) -- %d frames",
                    w, h, target_w, target_h, quality, n_frames)

        quality_mapping = {
            "LOW": nvvfx.effects.QualityLevel.LOW,
            "MEDIUM": nvvfx.effects.QualityLevel.MEDIUM,
            "HIGH": nvvfx.effects.QualityLevel.HIGH,
            "ULTRA": nvvfx.effects.QualityLevel.ULTRA,
        }
        selected_quality = quality_mapping.get(quality, nvvfx.effects.QualityLevel.ULTRA)

        MAX_PIXELS = 1024 * 1024 * 16
        out_pixels = target_w * target_h
        batch_size = max(1, MAX_PIXELS // out_pixels)
        upscaled_batches = []

        with nvvfx.VideoSuperRes(selected_quality) as sr:
            sr.output_width = target_w
            sr.output_height = target_h
            sr.load()

            for i in range(0, n_frames, batch_size):
                batch = images[i:i + batch_size]
                batch_cuda = batch.cuda().permute(0, 3, 1, 2).contiguous()
                batch_outputs = []
                for j in range(batch_cuda.shape[0]):
                    dlpack_out = sr.run(batch_cuda[j]).image
                    batch_outputs.append(torch.from_dlpack(dlpack_out).clone())
                batch_out = torch.stack(batch_outputs, dim=0).permute(0, 2, 3, 1).cpu()
                upscaled_batches.append(batch_out)

        result = torch.cat(upscaled_batches, dim=0)
        torch.cuda.empty_cache()

        elapsed = time.time() - t0
        logger.info("nvvfx VSR done in %.1fs (%.2f fps, %d frames -> %dx%d)",
                    elapsed, n_frames / elapsed if elapsed > 0 else 0,
                    n_frames, target_w, target_h)
        return result

    except ImportError:
        logger.info("nvvfx not installed. Falling back to bicubic...")
    except Exception as e:
        logger.warning("nvvfx failed: %s. Falling back to bicubic...", e)

    # --- Strategy 3: Torch bicubic (always available, lower quality) ---
    logger.info("Bicubic upscale: %dx%d -> %dx%d -- %d frames", w, h, target_w, target_h, n_frames)

    imgs_nchw = images.permute(0, 3, 1, 2)  # NHWC -> NCHW
    upscaled = torch.nn.functional.interpolate(
        imgs_nchw, size=(target_h, target_w),
        mode="bicubic", align_corners=False,
    ).clamp(0, 1)
    result = upscaled.permute(0, 2, 3, 1)  # NCHW -> NHWC

    elapsed = time.time() - t0
    logger.info("Bicubic upscale done in %.1fs (%d frames -> %dx%d)",
                elapsed, n_frames, target_w, target_h)
    return result


# ---------------------------------------------------------------------------
# Crossfade helpers
# ---------------------------------------------------------------------------

def _crossfade_images(all_images, overlap_frames):
    """Apply crossfade dissolve transitions between sequential image tensors."""
    if overlap_frames <= 0 or len(all_images) < 2:
        return torch.cat(all_images, dim=0)

    result_parts = []
    for i, clip in enumerate(all_images):
        if i == 0:
            if clip.shape[0] > overlap_frames:
                result_parts.append(clip[:-overlap_frames])
            if i + 1 < len(all_images):
                tail = clip[-overlap_frames:]
                head = all_images[i + 1][:overlap_frames]
                blend_len = min(tail.shape[0], head.shape[0])
                alpha = torch.linspace(0.0, 1.0, blend_len).view(-1, 1, 1, 1).to(tail.device)
                blended = (1.0 - alpha) * tail[:blend_len] + alpha * head[:blend_len]
                result_parts.append(blended)
        elif i == len(all_images) - 1:
            if clip.shape[0] > overlap_frames:
                result_parts.append(clip[overlap_frames:])
            else:
                result_parts.append(clip)
        else:
            body_start = overlap_frames
            body_end = clip.shape[0] - overlap_frames
            if body_end > body_start:
                result_parts.append(clip[body_start:body_end])
            elif body_start < clip.shape[0]:
                result_parts.append(clip[body_start:])
            if i + 1 < len(all_images):
                tail_start = max(body_end, body_start)
                tail = clip[tail_start:]
                if tail.shape[0] < overlap_frames:
                    pad = clip[-1:].expand(overlap_frames - tail.shape[0], -1, -1, -1)
                    tail = torch.cat([tail, pad], dim=0)
                tail = tail[:overlap_frames]
                head = all_images[i + 1][:overlap_frames]
                blend_len = min(tail.shape[0], head.shape[0])
                alpha = torch.linspace(0.0, 1.0, blend_len).view(-1, 1, 1, 1).to(tail.device)
                blended = (1.0 - alpha) * tail[:blend_len] + alpha * head[:blend_len]
                result_parts.append(blended)

    valid_parts = [p for p in result_parts if p.shape[0] > 0]
    if not valid_parts:
        return torch.cat(all_images, dim=0)
    return torch.cat(valid_parts, dim=0)


def _crossfade_audio(audio_list, overlap_frames, fps):
    """Apply audio crossfade matching video overlap."""
    valid = [a for a in audio_list if a is not None]
    if not valid or overlap_frames <= 0 or len(valid) < 2:
        return _concat_audio(audio_list)
    if not all(isinstance(a, dict) and "waveform" in a for a in valid):
        return _concat_audio(audio_list)

    sr = valid[0].get("sample_rate", 44100)
    overlap_samples = int((overlap_frames / fps) * sr)
    waveforms = [a["waveform"] for a in valid]

    # Normalize channel counts — expand mono to match max channels so cat won't fail
    max_ch = max(wf.shape[-2] if wf.dim() >= 2 else 1 for wf in waveforms)
    normalised = []
    for wf in waveforms:
        if wf.dim() == 1:
            wf = wf.unsqueeze(0)
        if wf.dim() == 2 and wf.shape[0] < max_ch:
            wf = wf.expand(max_ch, -1).contiguous()
        elif wf.dim() == 3 and wf.shape[1] < max_ch:
            wf = wf.expand(-1, max_ch, -1).contiguous()
        normalised.append(wf)
    waveforms = normalised

    result_parts = []

    for i, wf in enumerate(waveforms):
        n_samples = wf.shape[-1]
        if i == 0:
            if n_samples > overlap_samples:
                result_parts.append(wf[..., :-overlap_samples])
            if i + 1 < len(waveforms):
                tail = wf[..., -overlap_samples:]
                head = waveforms[i + 1][..., :overlap_samples]
                blend_len = min(tail.shape[-1], head.shape[-1])
                alpha = torch.linspace(0.0, 1.0, blend_len).to(tail.device)
                while alpha.dim() < tail.dim():
                    alpha = alpha.unsqueeze(0)
                blended = (1.0 - alpha) * tail[..., :blend_len] + alpha * head[..., :blend_len]
                result_parts.append(blended)
        elif i == len(waveforms) - 1:
            if n_samples > overlap_samples:
                result_parts.append(wf[..., overlap_samples:])
            else:
                result_parts.append(wf)
        else:
            body = wf[..., overlap_samples:-overlap_samples] if n_samples > 2 * overlap_samples else wf[..., overlap_samples:]
            result_parts.append(body)
            if i + 1 < len(waveforms):
                tail = wf[..., -overlap_samples:]
                head = waveforms[i + 1][..., :overlap_samples]
                blend_len = min(tail.shape[-1], head.shape[-1])
                alpha = torch.linspace(0.0, 1.0, blend_len).to(tail.device)
                while alpha.dim() < tail.dim():
                    alpha = alpha.unsqueeze(0)
                blended = (1.0 - alpha) * tail[..., :blend_len] + alpha * head[..., :blend_len]
                result_parts.append(blended)

    combined = torch.cat([p for p in result_parts if p.shape[-1] > 0], dim=-1)
    return {"waveform": combined, "sample_rate": sr}


def _concat_audio(audio_list):
    """Concatenate a list of AUDIO objects."""
    valid = [a for a in audio_list if a is not None]
    if not valid:
        return None
    if all(isinstance(a, dict) and "waveform" in a for a in valid):
        sr = valid[0].get("sample_rate", 44100)
        waveforms = [a["waveform"] for a in valid]
        # Normalize channel counts before concat
        max_ch = max(wf.shape[-2] if wf.dim() >= 2 else 1 for wf in waveforms)
        norm_wf = []
        for wf in waveforms:
            if wf.dim() == 1:
                wf = wf.unsqueeze(0)
            if wf.dim() == 2 and wf.shape[0] < max_ch:
                wf = wf.expand(max_ch, -1).contiguous()
            elif wf.dim() == 3 and wf.shape[1] < max_ch:
                wf = wf.expand(-1, max_ch, -1).contiguous()
            norm_wf.append(wf)
        combined = torch.cat(norm_wf, dim=-1)
        return {"waveform": combined, "sample_rate": sr}
    if all(isinstance(a, torch.Tensor) for a in valid):
        return torch.cat(valid, dim=-1)
    return valid[0]


# ---------------------------------------------------------------------------
# ComfyUI Node
# ---------------------------------------------------------------------------

class GooferVideoConcat:
    """
    Concatenates up to 6 VIDEO clips into a single VIDEO with optional
    RTX upscaling and crossfade transitions.
    """

    CATEGORY = "Goofer"
    FUNCTION = "concatenate"
    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("VIDEO",)

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_1": ("VIDEO",),
                "upscale_4k": (["disabled", "enabled"], {"default": "disabled",
                               "tooltip": "Upscale final video. Uses Real-ESRGAN (auto-downloads), nvvfx (if installed), or bicubic fallback."}),
                "upscale_resolution": (["1080", "1440", "2160", "4320"], {"default": "1080",
                                       "tooltip": "Target height: 1080=HD, 1440=2K, 2160=4K, 4320=8K"}),
                "upscale_quality": (["LOW", "MEDIUM", "HIGH", "ULTRA"], {"default": "ULTRA",
                                    "tooltip": "Upscale quality. ULTRA = best, LOW = fastest. Affects tile size for Real-ESRGAN."}),
            },
            "optional": {
                "video_2": ("VIDEO",),
                "video_3": ("VIDEO",),
                "video_4": ("VIDEO",),
                "video_5": ("VIDEO",),
                "video_6": ("VIDEO",),
                "crossfade_frames": ("INT", {
                    "default": 0, "min": 0, "max": 30, "step": 1,
                    "tooltip": "Frames to crossfade between clips (0=hard cut, 10-15=smooth dissolve)"}),
            },
        }

    def concatenate(self, video_1, upscale_4k="disabled", upscale_resolution="1080",
                    upscale_quality="ULTRA", video_2=None, video_3=None, video_4=None,
                    video_5=None, video_6=None, crossfade_frames=0):
        clips = [v for v in [video_1, video_2, video_3, video_4, video_5, video_6] if v is not None]
        logger.info("GooferVideoConcat: concatenating %d clips (crossfade=%d)",
                    len(clips), crossfade_frames)

        if len(clips) == 1 and upscale_4k != "enabled":
            return (clips[0],)

        # Validate crossfade_frames: ensure it can't exceed half of any clip's length.
        # This prevents empty tensors or garbage output from the crossfade logic.
        crossfade_frames = max(0, int(crossfade_frames))

        all_images = []
        all_audio = []
        fps = 30.0

        for i, clip in enumerate(clips):
            images, audio, clip_fps = _extract_components(clip)
            frame_count = images.shape[0] if isinstance(images, torch.Tensor) else len(images)
            logger.info("  Clip %d: %d frames, audio=%s, %.1f fps",
                        i + 1, frame_count, "yes" if audio is not None else "no", clip_fps)
            all_images.append(images)
            all_audio.append(audio)
            if i == 0:
                fps = clip_fps

        # Clamp crossfade to half the shortest clip so we never produce empty tensors
        if crossfade_frames > 0 and len(all_images) > 1:
            min_frames = min(img.shape[0] for img in all_images if isinstance(img, torch.Tensor))
            safe_overlap = min_frames // 2
            if crossfade_frames > safe_overlap:
                logger.warning("Crossfade %d exceeds safe limit (%d); clamping to %d",
                               crossfade_frames, safe_overlap, safe_overlap)
                crossfade_frames = safe_overlap

        # Resize mismatched spatial dims
        if all(isinstance(img, torch.Tensor) for img in all_images):
            ref_shape = all_images[0].shape[1:]
            for i in range(1, len(all_images)):
                if all_images[i].shape[1:] != ref_shape:
                    img = all_images[i].permute(0, 3, 1, 2)
                    img = torch.nn.functional.interpolate(
                        img, size=(ref_shape[0], ref_shape[1]),
                        mode="bilinear", align_corners=False)
                    all_images[i] = img.permute(0, 2, 3, 1)

            if crossfade_frames > 0 and len(all_images) > 1:
                combined_images = _crossfade_images(all_images, crossfade_frames)
            else:
                combined_images = torch.cat(all_images, dim=0)
        else:
            combined_images = []
            for img_batch in all_images:
                if isinstance(img_batch, torch.Tensor):
                    combined_images.extend([img_batch[j] for j in range(img_batch.shape[0])])
                else:
                    combined_images.extend(img_batch)
            combined_images = torch.stack(combined_images, dim=0)

        if crossfade_frames > 0 and len(all_audio) > 1:
            combined_audio = _crossfade_audio(all_audio, crossfade_frames, fps)
        else:
            combined_audio = _concat_audio(all_audio)

        if upscale_4k == "enabled":
            try:
                combined_images = _upscale(
                    combined_images,
                    target_resolution=int(upscale_resolution),
                    quality=upscale_quality,
                )
            except Exception as e:
                logger.error("GooferVideoConcat: upscale failed: %s", e)

        total_frames = combined_images.shape[0]
        logger.info("GooferVideoConcat: result = %d frames, %.1fs at %.0f fps",
                    total_frames, total_frames / fps, fps)

        try:
            result = type(video_1)(images=combined_images, audio=combined_audio, fps=fps)
            return (result,)
        except Exception:
            pass

        result = _build_video(combined_images, combined_audio, fps)
        return (result,)
