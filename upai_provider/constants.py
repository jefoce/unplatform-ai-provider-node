"""Bounds and tunables shared by the pack."""

import ipaddress

PROTOCOL_VERSION = 1
PROTOCOL_HEADER = "X-UPAI-Protocol"
IMPLEMENTATION_NAME = "unplatform-ai-provider-node"

MAX_UPLOAD_BYTES_DEFAULT = 104_857_600
UPLOAD_QUOTA_BYTES = 10 * 1024**3
MAX_JOBS_STORED = 500
SWEEP_INTERVAL_SEC = 600.0
DISK_FREE_REFRESH_SEC = 5.0
SCHEDULER_TICK_SEC = 0.5
REGISTER_OUTPUT_TIMEOUT = 10.0
ERROR_TEXT_MAX_CHARS = 300
MISSING_POLL_LIMIT = 3
MIN_FREE_DISK_BYTES = 5 * 1024**3
RESULTS_QUOTA_BYTES = 20 * 1024**3
INLINE_JSON_MARGIN = 1024

NODE_UPAI_MODEL = "UPAIModel"
NODE_UPAI_LIMITS = "UPAILimits"
NODE_UPAI_PROMPT = "UPAIPrompt"
NODE_UPAI_IMAGE_REF = "UPAIImageRef"
NODE_UPAI_VIDEO_REF = "UPAIVideoRef"
NODE_UPAI_AUDIO_REF = "UPAIAudioRef"
NODE_UPAI_START_FRAME = "UPAIStartFrame"
NODE_UPAI_END_FRAME = "UPAIEndFrame"
NODE_UPAI_SETTINGS = "UPAISettings"
NODE_UPAI_OUTPUT = "UPAIOutput"

WS_TYPE_UPAI_MODEL = "UPAI_MODEL"
WS_TYPE_UPAI_LIMITS = "UPAI_LIMITS"

MOCK_COMPLETE_SEC = 6.0
MOCK_FAIL_SEC = 3.0
MOCK_SLOW_SEC = 60.0
MOCK_PENDING_SEC = 0.5
MOCK_TICK_SEC = 0.5

ALLOWED_IMAGE_FORMATS = ("png", "jpg", "jpeg", "webp")
REFERENCE_MAX_BYTES = 20_971_520
CONTENT_TYPES = {
    "png": "image/png",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "webp": "image/webp",
    "mp4": "video/mp4",
    "mp3": "audio/mpeg",
    "wav": "audio/wav",
    "m4a": "audio/mp4",
    "ogg": "audio/ogg",
    "flac": "audio/flac",
    "webm": "video/webm",
    "mov": "video/quicktime",
}

IMAGE_RESOLUTIONS = ("512", "768", "1K", "1.5K", "2K", "4K")
VIDEO_RESOLUTIONS = ("480p", "720p", "768p", "1080p", "2K", "4K")
IMAGE_ASPECT_RATIOS = (
    "21:9",
    "2:1",
    "16:9",
    "3:2",
    "7:5",
    "4:3",
    "5:4",
    "1:1",
    "4:5",
    "3:4",
    "5:7",
    "2:3",
    "9:16",
    "1:2",
    "9:21",
    "1:8",
    "8:1",
    "1:4",
    "4:1",
    "9:19.5",
    "19.5:9",
    "9:20",
    "20:9",
)

SHORT_SIDE = {
    "512": 512,
    "768": 768,
    "1K": 1024,
    "1.5K": 1536,
    "2K": 1440,
    "4K": 2160,
    "480p": 480,
    "720p": 720,
    "768p": 768,
    "1080p": 1080,
}

LAN_NETWORKS = (
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("100.64.0.0/10"),
)
