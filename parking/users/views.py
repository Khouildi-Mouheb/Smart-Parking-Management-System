from django.shortcuts import render, redirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth import get_user_model
from rest_framework.decorators import api_view

User = get_user_model()

@api_view(['GET', 'POST'])
def login_view(request):
    if request.method == 'POST':
        email = request.data.get('email') or request.POST.get('email')
        password = request.data.get('password') or request.POST.get('password')
        user = authenticate(request, email=email, password=password)
        if user is not None:
            login(request, user)
            return redirect('/')
        return render(request, 'login.html', {'error': 'Invalid credentials. Please try again.'})
    return render(request, 'login.html')

@api_view(['GET', 'POST'])
def register_view(request):
    if request.user.is_authenticated:
        return redirect('/')

    if request.method == 'POST':
        email = request.data.get('email') or request.POST.get('email')
        password = request.data.get('password') or request.POST.get('password')
        password2 = request.data.get('password2') or request.POST.get('password2')
        full_name = request.data.get('full_name') or request.POST.get('full_name')
        company_name = request.data.get('company_name') or request.POST.get('company_name')
        role = request.data.get('role') or request.POST.get('role') or 'client'

        if not all([email, password, password2, full_name, company_name]):
            return render(request, 'register.html', {'error': 'All fields, including Company Name, are required.'})

        if password != password2:
            return render(request, 'register.html', {'error': 'Passwords do not match.'})

        if User.objects.filter(email=email).exists():
            return render(request, 'register.html', {'error': 'An account with this email already exists.'})

        company = None
        if company_name:
            from users.models import Company
            if role == 'admin':
                company, _ = Company.objects.get_or_create(name=company_name)
            else:
                try:
                    company = Company.objects.get(name__iexact=company_name)
                except Company.DoesNotExist:
                    return render(request, 'register.html', {'error': 'Company not found. Ask your company admin to provide the exact company name or register as company admin.'})

        user = User.objects.create_user(email=email, password=password, full_name=full_name, role=role, company=company)
        return redirect('/login/?success=1')

    return render(request, 'register.html')

def logout_view(request):
    logout(request)
    return redirect('/login/')