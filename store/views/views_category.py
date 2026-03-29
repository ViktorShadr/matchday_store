from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from store.mixins import ModeratorRequiredMixin
from store.models import Category


class CategoryListView(ListView):
    """
    Список всех категорий.
    
    Отображает пагинированный список категорий.
    
    Attributes:
        paginate_by: Количество категорий на странице (20)
        context_object_name: Имя переменной в контексте ('categories')
        
    Context:
        categories: Список всех категорий
    """
    model = Category
    template_name = "main_page/category_list.html"
    context_object_name = "categories"
    paginate_by = 20

    def get_queryset(self):
        return Category.objects.all().order_by("name")


class CategoryDetailView(DetailView):
    """
    Детальная страница категории.
    
    Отображает информацию о категории и связанные товары.
    
    Context:
        category: Объект категории
        products: Товары этой категории
    """
    model = Category
    template_name = "main_page/category_detail.html"
    context_object_name = "category"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["products"] = self.object.products.all().order_by("-created_at")
        return context


class CategoryCreateView(ModeratorRequiredMixin, CreateView):
    """
    Создание новой категории (только для модераторов).
    
    Позволяет модераторам создавать новые категории.
    
    Fields:
        name, description: Поля категории
        
    Returns:
        HttpResponseRedirect: Перенаправление на страницу созданной категории
    """
    model = Category
    template_name = "main_page/category_create.html"
    fields = ["name", "description"]
    context_object_name = "category"

    def get_success_url(self):
        return reverse_lazy("store:category_detail", kwargs={"pk": self.object.pk})


class CategoryUpdateView(ModeratorRequiredMixin, UpdateView):
    """
    Редактирование категории (только для модераторов).
    
    Позволяет модераторам редактировать информацию о категории.
    
    Fields:
        name, description: Поля категории
        
    Returns:
        HttpResponseRedirect: Перенаправление на страницу категории после сохранения
    """
    model = Category
    template_name = "main_page/category_update.html"
    fields = ["name", "description"]
    context_object_name = "category"

    def get_success_url(self):
        return reverse_lazy("store:category_detail", kwargs={"pk": self.object.pk})


class CategoryDeleteView(ModeratorRequiredMixin, DeleteView):
    """
    Удаление категории (только для модераторов).
    
    Позволяет модераторам удалять категории.
    
    Returns:
        HttpResponseRedirect: Перенаправление на список категорий после удаления
    """
    model = Category
    template_name = "main_page/category_delete.html"
    context_object_name = "category"
    success_url = reverse_lazy("store:category_list")
