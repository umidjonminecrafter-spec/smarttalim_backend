import datetime
import json
import zipfile
import io
import urllib.request
from django.contrib.auth import authenticate, get_user_model
from django.utils import timezone
from rest_framework import viewsets, permissions, status, decorators, serializers
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken

from organizations.models import (
    Organization, Tariff, Subscription, ExamSetting,
    ReceiptSetting, BackupSetting, TelegramNotificationSetting
)
from organizations.mixins import TenantViewSetMixin
from organizations.permissions import HasOrganizationPagePermission
from organizations.serializers import (
    OrganizationSerializer, TariffSerializer, SubscriptionSerializer,
    ExamSettingSerializer, ReceiptSettingSerializer, BackupSettingSerializer,
    TelegramNotificationSettingSerializer
)
from organizations.backup import run_backup_for_setting

User = get_user_model()


# accounts app o'rniga yengil lokal serializer
class UserLightSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ('id', 'username', 'first_name', 'last_name', 'organization')
        read_only_fields = ('id',)


class OrganizationViewSet(viewsets.ModelViewSet):
    queryset = Organization.objects.all()
    serializer_class = OrganizationSerializer
    permission_classes = (permissions.IsAuthenticated, HasOrganizationPagePermission)
    permission_page_name = 'Sozlamalar'
    allow_without_organization = True

    def get_queryset(self):
        user = self.request.user
        if user.is_authenticated and getattr(user, 'organization_id', None):
            return Organization.objects.filter(id=user.organization_id)
        return Organization.objects.none()

    def perform_create(self, serializer):
        org = serializer.save()
        user = self.request.user
        if user.is_authenticated and not getattr(user, 'organization', None):
            user.organization = org
            user.role = 'owner'
            user.save()

        default_tariff = Tariff.objects.filter(name__iexact='Premium').first() or Tariff.objects.first()
        today = timezone.now().date()
        Subscription.objects.get_or_create(
            organization=org,
            defaults={
                'tariff': default_tariff,
                'start_date': today,
                'end_date': today + datetime.timedelta(days=365),
                'is_active': False,
                'balance': 0.00
            }
        )

    @decorators.action(detail=False, methods=['get', 'put', 'patch'], url_path='settings')
    def organization_general_settings(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        if request.method in ('PUT', 'PATCH'):
            ser = OrganizationSerializer(org, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        return Response(OrganizationSerializer(org).data)

    @decorators.action(detail=False, methods=['get', 'put'], url_path='exam-settings')
    def exam_settings(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting, _ = ExamSetting.objects.get_or_create(organization=org)
        if request.method == 'PUT':
            ser = ExamSettingSerializer(setting, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        return Response(ExamSettingSerializer(setting).data)

    @decorators.action(detail=False, methods=['get', 'put'], url_path='receipt-settings')
    def receipt_settings(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting, _ = ReceiptSetting.objects.get_or_create(organization=org)
        if request.method == 'PUT':
            ser = ReceiptSettingSerializer(setting, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        return Response(ReceiptSettingSerializer(setting).data)

    @decorators.action(detail=False, methods=['get', 'put'], url_path='backup-settings')
    def backup_settings(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting, _ = BackupSetting.objects.get_or_create(organization=org)
        if request.method == 'PUT':
            ser = BackupSettingSerializer(setting, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        return Response(BackupSettingSerializer(setting).data)

    @decorators.action(detail=False, methods=['post'], url_path='backup-now')
    def backup_now(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting, _ = BackupSetting.objects.get_or_create(organization=org)
        success, msg = run_backup_for_setting(setting)
        return Response({"detail": msg}, status=200 if success else 400)

    @decorators.action(detail=False, methods=['get'], url_path='backup-download')
    def backup_download(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)

        from django.apps import apps
        from django.core import serializers as dj_serializers
        from django.http import HttpResponse

        backup_data = []
        for model in apps.get_models():
            if 'organization' in [f.name for f in model._meta.fields]:
                try:
                    qs = model.objects.filter(organization_id=org.id)
                    if qs.exists():
                        backup_data.extend(json.loads(dj_serializers.serialize('json', qs)))
                except Exception as e:
                    print(f"Backup serialize error: {e}")

        if not backup_data:
            return Response({"detail": "Ma'lumot topilmadi."}, status=400)

        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c for c in org.name if c.isalnum() or c in (' ', '_', '-')).strip().replace(' ', '_')
        json_fn, zip_fn = f"backup_{safe_name}_{ts}.json", f"backup_{safe_name}_{ts}.zip"

        try:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.writestr(json_fn, json.dumps(backup_data, ensure_ascii=False, indent=2))
            buf.seek(0)
            res = HttpResponse(buf.getvalue(), content_type='application/zip')
            res['Content-Disposition'] = f'attachment; filename="{zip_fn}"'
            return res
        except Exception as e:
            return Response({"detail": f"Xatolik: {e}"}, status=500)

    @decorators.action(detail=False, methods=['get', 'put'], url_path='telegram-settings')
    def telegram_settings(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting, _ = TelegramNotificationSetting.objects.get_or_create(organization=org)
        if request.method == 'PUT':
            ser = TelegramNotificationSettingSerializer(setting, data=request.data, partial=True)
            ser.is_valid(raise_exception=True)
            ser.save()
            return Response(ser.data)
        return Response(TelegramNotificationSettingSerializer(setting).data)

    @decorators.action(detail=False, methods=['post'], url_path='telegram-test')
    def telegram_test(self, request):
        org = getattr(request.user, 'organization', None)
        if not org: return Response({"detail": "Tashkilot topilmadi."}, status=400)
        setting = TelegramNotificationSetting.objects.filter(organization=org).first()
        if not setting or not setting.bot_token or not setting.chat_ids:
            return Response({"detail": "Bot sozlamalari to'liq emas."}, status=400)

        text = f"<b>SmartTalim Test</b> 🔔\nTashkilot: <i>{org.name}</i>\nTizim muvaffaqiyatli sozlandi! ✅"
        chat_ids = [c.strip() for c in setting.chat_ids.replace(',', ' ').split() if c.strip()]
        errors = []
        for cid in chat_ids:
            try:
                req = urllib.request.Request(
                    f"https://api.telegram.org/bot{setting.bot_token}/sendMessage",
                    data=json.dumps({'chat_id': cid, 'text': text, 'parse_mode': 'HTML'}).encode(),
                    headers={'Content-Type': 'application/json'}, method='POST'
                )
                urllib.request.urlopen(req, timeout=8)
            except Exception as e:
                errors.append(f"{cid}: {e}")
        if errors: return Response({"detail": f"Xatolik: {'; '.join(errors)}"}, status=400)
        return Response({"detail": "Test xabar yuborildi! 🚀"}, status=200)


class TariffViewSet(viewsets.ModelViewSet):
    permission_classes = (permissions.IsAuthenticated, HasOrganizationPagePermission)
    permission_page_name = 'Sozlamalar'
    queryset = Tariff.objects.all()
    serializer_class = TariffSerializer


class SubscriptionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_page_name = 'Sozlamalar'
    queryset = Subscription.objects.all()
    serializer_class = SubscriptionSerializer

    def list(self, request, *args, **kwargs):
        org_id = self.get_organization_id()
        if not org_id: return Response([])
        today = timezone.now().date()
        sub, _ = Subscription.objects.get_or_create(
            organization_id=org_id,
            defaults={'start_date': today, 'end_date': today + datetime.timedelta(days=365), 'is_active': True}
        )
        return Response([self.get_serializer(sub).data])


class OrganizationLoginView(APIView):
    permission_classes = (permissions.AllowAny,)

    def post(self, request):
        user = authenticate(
            username=request.data.get('username'),
            password=request.data.get('password')
        )

        if not user:
            return Response(
                {"detail": "Login yoki parol noto'g'ri."},
                status=400
            )

        if not user.is_active:
            return Response(
                {"detail": "Hisob o'chirilgan."},
                status=400
            )

        refresh = RefreshToken.for_user(user)

        return Response({
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': {
                'id': user.id,
                'username': user.username,
                'email': user.email,
                'first_name': user.first_name,
                'last_name': user.last_name,
            }
        }, status=200)