from modeltranslation.translator import register, TranslationOptions
from .models import Category, Listing, Event, Promotion, Blog

@register(Category)
class CategoryTranslationOptions(TranslationOptions):
    fields = ('name', 'description')

@register(Listing)
class ListingTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'address', 'open_time')

@register(Event)
class EventTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'location')

@register(Promotion)
class PromotionTranslationOptions(TranslationOptions):
    fields = ('title', 'description', 'address')

@register(Blog)
class BlogTranslationOptions(TranslationOptions):
    fields = ('title', 'subtitle', 'content', 'author')