from rest_framework.pagination import PageNumberPagination


class StandardResultsSetPagination(PageNumberPagination):
    """
    Standard pagination class for all viewsets.
    - Default page size: 20
    - Client can request page size via ?page_size= parameter
    - Max page size: 100 to prevent excessive data transfer
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
