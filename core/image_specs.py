"""
Image specifications for automatic thumbnail generation and optimization.
These specs will create multiple size variants for efficient loading on mobile devices.
"""
from imagekit import ImageSpec
from imagekit.processors import ResizeToFill, ResizeToFit
from pilkit.processors import Thumbnail


class ListingThumbnail(ImageSpec):
    """Small thumbnail for listing cards (54x54px)"""
    processors = [ResizeToFill(54, 54)]
    format = 'WEBP'
    options = {'quality': 85}


class ListingMedium(ImageSpec):
    """Medium size for listing preview (430px width)"""
    processors = [ResizeToFit(430, 430)]
    format = 'WEBP'
    options = {'quality': 90}


class ListingLarge(ImageSpec):
    """Large size for listing detail view (800px width)"""
    processors = [ResizeToFit(800, 800)]
    format = 'WEBP'
    options = {'quality': 90}


class PromotionThumbnail(ImageSpec):
    """Small thumbnail for promotion cards (54x54px)"""
    processors = [ResizeToFill(54, 54)]
    format = 'WEBP'
    options = {'quality': 85}


class PromotionMedium(ImageSpec):
    """Medium size for promotion carousel (430px width)"""
    processors = [ResizeToFit(430, 430)]
    format = 'WEBP'
    options = {'quality': 90}


class EventThumbnail(ImageSpec):
    """Small thumbnail for event cards (54x54px)"""
    processors = [ResizeToFill(54, 54)]
    format = 'WEBP'
    options = {'quality': 85}


class EventMedium(ImageSpec):
    """Medium size for event carousel (430px width)"""
    processors = [ResizeToFit(430, 430)]
    format = 'WEBP'
    options = {'quality': 90}


class BlogThumbnail(ImageSpec):
    """Small thumbnail for blog cards (54x54px)"""
    processors = [ResizeToFill(54, 54)]
    format = 'WEBP'
    options = {'quality': 85}


class BlogMedium(ImageSpec):
    """Medium size for blog carousel (430px width)"""
    processors = [ResizeToFit(430, 430)]
    format = 'WEBP'
    options = {'quality': 90}
