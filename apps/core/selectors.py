from .models import Company

def get_company():
    return Company.objects.filter(pk=1).first()
