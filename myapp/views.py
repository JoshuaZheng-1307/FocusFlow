# myapp/views.py
import os
from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from .models import UserProfile, LearningDirection
from django.db.models import Sum
from django.views.decorators.http import require_POST
import json


def home(request):
    """公共主页"""
    return render(request, 'myapp/home.html')


def register(request):
    """注册视图"""
    if request.method == 'POST':
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('myapp:index')
    else:
        form = RegisterForm()
    return render(request, 'myapp/register.html', {'form': form})


@login_required
def index_view(request):
    """登录后首页 - 增加了积分数据查询"""
    # 获取用户的所有学习方向
    directions = request.user.directions.all()

    # 获取用户的积分信息
    profile, created = UserProfile.objects.get_or_create(user=request.user)

    return render(request, 'myapp/index.html', {
        'directions': directions,
        'total_score': profile.total_score  # 将积分传给前端
    })


def focusflow(request):
    """学习页面"""
    return render(request, 'myapp/focusflow.html')


# --- API 接口：获取真实数据 ---
@login_required
def home_data_api(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    # --- 1. 计算单个学习方向的积分 ---
    direction_data = []
    for d in user.directions.all():
        if d.mastered:
            score = d.time_seconds
        else:
            hours = d.time_seconds / 3600
            if hours > 0:
                score = round(5 * (hours ** 1.5) + 20 * hours)
            else:
                score = 0
        direction_data.append({
            "id": d.id,
            "name": d.name,
            "time_seconds": d.time_seconds,
            "mastered": d.mastered,
            "score": score
        })

    # --- 2. 获取全局排行榜数据 ---
    leaderboard = UserProfile.objects.select_related('user').order_by('-total_score')[:10]
    leaderboard_data = []
    for item in leaderboard:
        leaderboard_data.append({
            "username": item.user.username,
            "total_score": item.total_score,
            "avatar": item.avatar.url if item.avatar else None
        })

    # --- 3. 组装数据 ---
    data = {
        "user": {
            "username": user.username,
            "email": user.email,
            "avatar": profile.avatar.url if profile.avatar else None,
        },
        "total_score": profile.total_score,
        "directions": direction_data,
        "leaderboard": leaderboard_data,
        "friends": [],
    }
    return JsonResponse(data)


# --- 头像上传处理 (已修复) ---
@login_required
@require_POST
# 建议加上 csrf_exempt 以排除 CSRF 导致的 403 错误返回 HTML 的问题
# 如果你的项目对安全性要求极高，建议在前端 JS 中携带 csrftoken，而不是用这个装饰器
@csrf_exempt
def upload_avatar(request):
    if request.method == 'POST':
        # 1. 检查是否有文件
        if 'avatar' in request.FILES:
            avatar_file = request.FILES['avatar']

            # 2. 获取当前用户
            user = request.user
            profile, created = UserProfile.objects.get_or_create(user=user)

            # 3. 保存文件逻辑
            try:
                # 如果你想覆盖旧头像，先删除旧的（可选）
                if profile.avatar and os.path.isfile(profile.avatar.path):
                    os.remove(profile.avatar.path)

                # 保存新头像
                profile.avatar = avatar_file
                profile.save()

                # 4. 【关键点】构建返回的 URL
                # 确保这里生成的 URL 是浏览器可以直接访问到的
                # 如果 settings.MEDIA_URL 配置正确，直接用 profile.avatar.url 即可
                avatar_url = profile.avatar.url

                return JsonResponse({
                    'status': 'success',
                    'message': '上传成功',
                    'avatar_url': avatar_url
                })

            except Exception as e:
                print(f"上传出错: {e}")
                return JsonResponse({
                    'status': 'error',
                    'message': str(e)
                }, status=500)
        else:
            return JsonResponse({'status': 'error', 'message': '未检测到文件'}, status=400)

    # 如果不是 POST 请求，也返回 JSON，防止返回 HTML 页面
    return JsonResponse({'status': 'error', 'message': '无效请求'}, status=405)

# --- 保存学习数据 ---
@login_required
def save_direction_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            dir_id = data.get('id')
            time_seconds = data.get('time')
            mastered = data.get('mastered', False)

            direction, created = LearningDirection.objects.update_or_create(
                user=request.user,
                id=dir_id,
                defaults={
                    'time_seconds': time_seconds,
                    'mastered': mastered
                }
            )

            # 重新计算总积分
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            unlocked_time = sum([d.time_seconds for d in request.user.directions.filter(mastered=False)])
            mastery_bonus = sum([d.time_seconds for d in request.user.directions.filter(mastered=True)])
            hours = unlocked_time / 3600
            base_score = round(5 * (hours ** 1.5) + 20 * hours) if hours > 0 else 0
            profile.total_score = base_score + mastery_bonus
            profile.save()

            return JsonResponse({'status': 'success', 'total_score': profile.total_score})
        except Exception as e:
            return JsonResponse({'status': 'error', 'msg': str(e)})
    return JsonResponse({'status': 'error', 'msg': 'Invalid request'})