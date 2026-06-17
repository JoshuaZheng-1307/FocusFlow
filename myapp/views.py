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

def calculate_direction_score(direction):
    """根据方向对象计算积分"""
    if direction.mastered:
        # 精通项目的逻辑（根据你的描述可能是直接等于时长或其他固定值）
        return direction.time_seconds
    else:
        # 未精通项目逻辑
        hours = direction.time_seconds / 60  # 注意：这里应该是除以3600得到小时
        if hours > 0:
            # 这里的公式需要和你前端 focusflow.js 里的 updatePoints 保持一致
            score = round(5 * (hours ** 1.5) + 20 * hours)
            return score
        else:
            return 0
# --- API 接口：获取真实数据 ---
@login_required
def home_data_api(request):
    user = request.user
    profile, created = UserProfile.objects.get_or_create(user=user)

    # --- 1. 计算单个学习方向的积分 & 动态计算总分 ---
    direction_data = []
    calculated_total_score = 0  # <--- 新增：初始化动态总分变量

    for d in user.directions.all():
        # 调用统一的计算函数获取分数
        current_score = calculate_direction_score(d)

        # 累加到总分
        calculated_total_score += current_score

        direction_data.append({
            "id": d.id,
            "name": d.name,
            "time_seconds": d.time_seconds,
            "mastered": d.mastered,
            "score": current_score  # 使用计算后的分数
        })

    # --- 2. 获取全局排行榜数据 (修正版) ---
    # 1. 先获取用户列表（这里为了简单，我们先取前20名的 UserProfile）
    # 注意：真实项目中如果用户量大，这里需要优化，但现在先保证逻辑正确
    top_profiles = UserProfile.objects.select_related('user').order_by('-total_score')[:20]

    leaderboard_data = []

    for item in top_profiles:
        # 2. 获取该用户的所有学习方向
        user_directions = LearningDirection.objects.filter(user=item.user)

        # 3. 初始化该用户的实时总分
        user_current_score = 0

        # 4. 遍历该用户的所有方向，累加积分
        for d in user_directions:
            # 复用之前写好的计算逻辑函数
            user_current_score += calculate_direction_score(d)

        # 5. 将计算后的新分数加入列表
        # 注意：这里不再使用 item.total_score，而是使用 user_current_score
        leaderboard_data.append({
            "username": item.user.username,
            "total_score": user_current_score,  # <--- 正确：使用了实时计算的新分数
            "avatar": item.avatar.url if item.avatar else None
        })

    # 6. 在内存中对计算好的新数据进行排序（因为数据库的排序是基于旧数据的）
    leaderboard_data.sort(key=lambda x: x['total_score'], reverse=True)
    # 7. 取前 10 名
    leaderboard_data = leaderboard_data[:10]

    # --- 3. 组装数据 ---
    data = {
        "user": {
            "username": user.username,
            "email": user.email,
            "avatar": profile.avatar.url if profile.avatar else None,
        },
        # 【关键修改】不再读取 profile.total_score，而是使用刚刚算出来的 calculated_total_score
        "total_score": calculated_total_score,
        "directions": direction_data,
        "leaderboard": leaderboard_data,
        "friends": [],
    }
    return JsonResponse(data)

# --- 新增 API：获取用户的学习数据 ---
@login_required
def get_user_data(request):
    user = request.user

    # 【核心修复】确保能正确获取该用户的所有方向，不要加任何过滤条件！
    # 如果你在 models.py 中定义了 related_name='directions'，就用 user.directions
    # 如果没有定义，默认用 user.learningdirection_set
    all_directions = LearningDirection.objects.filter(user=user)
    # 【调试代码】在控制台打印出查到的方向数量和具体内容
    print(f"[DEBUG] 用户 {user.username} 共有 {all_directions.count()} 个学习方向:")

    data = []
    for d in all_directions:
        data.append({
            "id": d.id,
            "name": d.name,
            "time_seconds": d.time_seconds,
            "mastered": d.mastered
        })

    # 获取总分...
    try:
        profile = user.userprofile
        total_score = profile.total_score
    except:
        total_score = 0

    return JsonResponse({
        "directions": data,
        "total_score": total_score
    })
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
            # 1. 解析前端发来的 JSON 数据
            data = json.loads(request.body)

            # 获取各个字段 (注意：这里要加上 id 的获取)
            dir_id = data.get('id')
            d_name = data.get('name',"未命名方向")
            time_seconds = data.get('time', 0)
            mastered = data.get('mastered', False)

            new_id = None

            if dir_id:
                # 情况 A: 有 ID -> 更新现有记录
                direction, created = LearningDirection.objects.update_or_create(
                    user=request.user,
                    id=dir_id,
                    defaults={
                        'name': d_name,
                        'time_seconds': time_seconds,
                        'mastered': mastered
                    }
                )
            else:
                # 情况 B: 无 ID (新方向) -> 创建新记录
                direction = LearningDirection.objects.create(
                    user=request.user,
                    name=d_name,
                    time_seconds=time_seconds,
                    mastered=mastered
                )
                new_id = direction.id
            # 3. 重新计算总积分逻辑保持不变
            profile, _ = UserProfile.objects.get_or_create(user=request.user)

            # 获取该用户所有的方向进行计算
            all_directions = LearningDirection.objects.filter(user=request.user)

            unlocked_time = sum([d.time_seconds for d in all_directions if not d.mastered])
            mastery_bonus = sum([d.time_seconds for d in all_directions if d.mastered])

            hours = unlocked_time / 3600
            base_score = round(5 * (hours ** 1.5) + 20 * hours) if hours > 0 else 0

            profile.total_score = base_score + mastery_bonus
            profile.save()

            return JsonResponse({
                'status': 'success',
                'total_score': profile.total_score,
                'new_id': new_id
            })

        except Exception as e:
            # 打印具体错误到控制台方便调试
            print(f"Save Error: {e}")
            return JsonResponse({'status': 'error', 'msg': str(e)})

    return JsonResponse({'status': 'error', 'msg': 'Invalid request method'})