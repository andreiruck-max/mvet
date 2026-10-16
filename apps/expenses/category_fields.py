"""Grouped, searchable chart choices for items that do not move stock."""
from django import forms
from django.forms.models import ModelChoiceIterator
from .models import ChartOfAccount


class GroupedCategoryIterator(ModelChoiceIterator):
    def __iter__(self):
        yield ('', self.field.empty_label)
        chart={row.pk:row for row in ChartOfAccount.objects.all()}
        groups={}
        for category in self.queryset:
            node=chart.get(category.pk);parents=[];seen=set();valid=True
            while node:
                if node.pk in seen or not node.active:
                    valid=False;break
                seen.add(node.pk)
                if node.pk!=category.pk:parents.append(f'{node.code} · {node.name}')
                node=chart.get(node.parent_id)
            if not valid:continue
            label=' / '.join(reversed(parents)) or 'Categorias sem grupo'
            groups.setdefault(label,[]).append((category.pk,str(category)))
        yield from groups.items()


class SearchableCategorySelect(forms.Select):
    template_name='widgets/searchable_category.html'


class NonstockCategoryField(forms.ModelChoiceField):
    iterator=GroupedCategoryIterator

    def __init__(self,**kwargs):
        super().__init__(label='Categoria sem estoque',required=False,
            queryset=ChartOfAccount.objects.filter(active=True,postable=True).exclude(nature__in=['REVENUE','DEPRECIATION','GROUP']),
            empty_label='Selecione uma subcategoria',widget=SearchableCategorySelect,**kwargs)
