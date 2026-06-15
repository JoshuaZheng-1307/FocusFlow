from django.db import models

# Create your models here.
# models.py
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
import os

# 1. 用户扩展资料模型 (用于存储积分和头像)
class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    total_score = models.IntegerField(default=0)
    avatar = models.ImageField(upload_to='avatars/', null=True, blank=True)

    def __str__(self):
        return f"{self.user.username}'s Profile"

# 2. 学习方向模型 (用于存储每个用户的学习方向和对应时间/积分)
class LearningDirection(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='directions')
    name = models.CharField(max_length=100)
    time_seconds = models.IntegerField(default=0) # 存储总秒数
    mastered = models.BooleanField(default=False)

    def __str__(self):
        return self.name

# --- 信号量：当用户注册时，自动创建 UserProfile ---
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    instance.profile.save()