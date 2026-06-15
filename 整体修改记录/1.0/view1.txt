# myapp/views.py

from django.shortcuts import render, redirect
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from .forms import RegisterForm
from django.contrib.auth.models import User
from django.http import JsonResponse
from .forms import RegisterForm # 确保你有一个 RegisterForm
from .models import UserProfile, LearningDirection # 导入模型
from django.db.models import Sum
from django.views.decorators.http import require_POST, require_GET
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
            # 【关键点】注册成功后跳转到 index (即 dashboard)
            return redirect('myapp:index')
    else:
        form = RegisterForm()
    return render(request, 'myapp/register.html', {'form': form})

@login_required
def index_view(request):
    """登录后首页"""
    # 获取用户的所有学习方向
    directions = request.user.directions.all()
    return render(request, 'myapp/index.html', {
        'directions': directions
    })

def focusflow(request):
    """学习页面 (对应 focusflow/)"""
    return render(request, 'myapp/focusflow.html')
# views.py
from django.http import JsonResponse
import json


# 假设这是你的用户模型或其他模型
# from .models import User, Score, Friend, Leaderboard

# --- API 接口：获取真实数据 ---
@login_required
def home_data_api(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    # --- 1. 计算单个学习方向的积分 (用于 Index 成就展示) ---
    # 逻辑：未锁定方向按公式算分，已锁定方向按秒数算分
    direction_data = []
    for d in user.directions.all():
        # 这里的积分计算逻辑复用 focusflow 的规则
        if d.mastered:
            score = d.time_seconds  # 精通后按秒数算
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
            "score": score  # 增加 score 字段
        })

    # --- 2. 获取全局排行榜数据 (所有用户按总积分排序) ---
    # 这里假设总积分存储在 UserProfile.total_score 中
    leaderboard = UserProfile.objects.select_related('user').order_by('-total_score')[:10]  # 取前10
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
        "directions": direction_data,  # 现在包含积分
        "leaderboard": leaderboard_data,  # 新增排行榜数据
        "friends": [],
    }
    return JsonResponse(data)
# --- 头像上传处理 ---
@login_required
def upload_avatar(request):
    if request.method == 'POST' and request.FILES.get('avatar'):
        profile, created = UserProfile.objects.get_or_create(user=request.user)
        # 如果已有头像，删除旧文件 (可选，需要导入 os)
        if profile.avatar:
            if os.path.isfile(profile.avatar.path):
                os.remove(profile.avatar.path)
        profile.avatar = request.FILES['avatar']
        profile.save()
        return JsonResponse({'status': 'success', 'avatar_url': profile.avatar.url})
    return JsonResponse({'status': 'error'})


# --- 新增：保存单次学习数据的 API ---
@login_required
def save_direction_data(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            dir_id = data.get('id')
            time_seconds = data.get('time')
            mastered = data.get('mastered', False)

            # 更新数据库
            direction, created = LearningDirection.objects.get_or_create(
                user=request.user,
                id=dir_id
            )
            # 如果是新记录或者时间变多了，更新时间
            if time_seconds > direction.time_seconds:
                direction.time_seconds = time_seconds
                direction.mastered = mastered
                direction.save()

            # 更新用户总积分 (简单累加，或者根据你的规则重新计算)
            # 这里简单示例：直接加
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            # profile.total_score += (time_seconds - direction.time_seconds) # 精确增量
            # 简单粗暴：重新计算总分
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