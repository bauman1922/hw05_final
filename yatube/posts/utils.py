from django.core.paginator import Paginator

ITEMS_PER_PAGE = 10


def get_paginator(queryset, request):
    paginator = Paginator(queryset, ITEMS_PER_PAGE)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    return {
        'paginator': paginator,
        'page_number': page_number,
        'page_obj': page_obj,
    }
