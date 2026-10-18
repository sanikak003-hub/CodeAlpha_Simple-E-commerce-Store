from decimal import Decimal
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django import forms
from .models import Product, Order, OrderItem


class RegisterForm(forms.Form):
    username = forms.CharField(max_length=150)
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    confirm_password = forms.CharField(widget=forms.PasswordInput, label="Confirm password")

    def clean_username(self):
        from django.contrib.auth.models import User
        username = self.cleaned_data["username"]
        if User.objects.filter(username=username).exists():
            raise forms.ValidationError("That username is already taken.")
        return username

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password") and cleaned.get("confirm_password") and cleaned["password"] != cleaned["confirm_password"]:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned


def product_list(request):
    products = Product.objects.all().order_by("-created_at")
    return render(request, "shop/product_list.html", {"products": products})


def product_detail(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    return render(request, "shop/product_detail.html", {"product": product})


def _cart_data(request):
    cart = request.session.get("cart", {})
    products = []
    total = Decimal("0.00")
    for product_id, quantity in cart.items():
        try:
            product = Product.objects.get(pk=int(product_id))
            quantity = int(quantity)
        except (Product.DoesNotExist, ValueError, TypeError):
            continue
        if quantity < 1:
            continue
        line_total = product.price * quantity
        products.append({"product": product, "quantity": quantity, "line_total": line_total})
        total += line_total
    return products, total


def cart_view(request):
    items, total = _cart_data(request)
    return render(request, "shop/cart.html", {"items": items, "total": total})


@require_POST
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    if product.stock < 1:
        messages.error(request, "This product is out of stock.")
        return redirect("product_detail", product_id=product.id)
    cart = request.session.get("cart", {})
    key = str(product.id)
    cart[key] = min(int(cart.get(key, 0)) + 1, product.stock)
    request.session["cart"] = cart
    messages.success(request, f"{product.name} added to your cart.")
    return redirect("cart")


@require_POST
def update_cart(request, product_id):
    product = get_object_or_404(Product, pk=product_id)
    try:
        quantity = int(request.POST.get("quantity", "1"))
    except ValueError:
        quantity = 1
    cart = request.session.get("cart", {})
    if quantity <= 0:
        cart.pop(str(product.id), None)
    elif product.stock > 0:
        cart[str(product.id)] = min(quantity, product.stock)
    else:
        cart.pop(str(product.id), None)
    request.session["cart"] = cart
    return redirect("cart")


@require_POST
def remove_from_cart(request, product_id):
    cart = request.session.get("cart", {})
    cart.pop(str(product_id), None)
    request.session["cart"] = cart
    return redirect("cart")


@login_required
def checkout(request):
    items, total = _cart_data(request)
    if not items:
        messages.info(request, "Your cart is empty.")
        return redirect("product_list")

    if request.method == "POST":
        full_name = request.POST.get("full_name", "").strip()
        address = request.POST.get("address", "").strip()
        phone = request.POST.get("phone", "").strip()
        if not full_name or not address or not phone:
            messages.error(request, "Please fill in all checkout fields.")
            return render(request, "shop/checkout.html", {"items": items, "total": total})

        with transaction.atomic():
            # Lock/recheck stock immediately before saving the order.
            product_ids = [entry["product"].id for entry in items]
            locked_products = {
                p.id: p for p in Product.objects.select_for_update().filter(id__in=product_ids)
            }
            for entry in items:
                product = locked_products.get(entry["product"].id)
                if product is None or product.stock < entry["quantity"]:
                    messages.error(request, f"Not enough stock for {entry['product'].name}. Please update your cart.")
                    return redirect("cart")

            order = Order.objects.create(
                user=request.user,
                full_name=full_name,
                address=address,
                phone=phone,
                total=total,
            )
            for entry in items:
                product = locked_products[entry["product"].id]
                quantity = entry["quantity"]
                OrderItem.objects.create(
                    order=order,
                    product=product,
                    product_name=product.name,
                    price=product.price,
                    quantity=quantity,
                )
                product.stock -= quantity
                product.save(update_fields=["stock"])

        request.session["cart"] = {}
        return redirect("order_success", order_id=order.id)

    return render(request, "shop/checkout.html", {"items": items, "total": total})


@login_required
def order_history(request):
    orders = Order.objects.filter(user=request.user).prefetch_related("items").order_by("-created_at")
    return render(request, "shop/orders.html", {"orders": orders})


@login_required
def order_success(request, order_id):
    order = get_object_or_404(Order, pk=order_id, user=request.user)
    return render(request, "shop/order_success.html", {"order": order})


def register(request):
    if request.user.is_authenticated:
        return redirect("product_list")
    form = RegisterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        from django.contrib.auth.models import User
        user = User.objects.create_user(
            username=form.cleaned_data["username"],
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password"],
        )
        login(request, user)
        messages.success(request, "Your account was created.")
        return redirect("product_list")
    return render(request, "registration/register.html", {"form": form})
