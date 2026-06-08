from rest_framework import viewsets, permissions, status, mixins, exceptions
from rest_framework.response import Response
from rest_framework.decorators import action
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from django.utils import timezone
from django.db.models import Q

from organizations.mixins import TenantViewSetMixin
from organizations.permissions import IsAdminOrOwnerOrReadOnly
from crm.models import (
    Pipeline, Source, LostReason, Section, LeadForm, Lead,
    CRMActivity, CRMLeadsHistory, CRMLeadLost
)
from crm.serializers import (
    PipelineSerializer, SourceSerializer, LostReasonSerializer,
    SectionSerializer, LeadFormSerializer, LeadSerializer,
    CRMActivitySerializer, CRMLeadsHistorySerializer, CRMLeadLostSerializer
)


class PipelineViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Pipeline.objects.all()
    serializer_class = PipelineSerializer

    def destroy(self, request, *args, **kwargs):
        pipeline = self.get_object()
        if pipeline.leads.filter(is_archived=False).exists():
            return Response(
                {"detail": "Naborda faol lidlar mavjud. Avval lidlarni boshqa naborga o'tkazing yoki arxivlang."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)


class SourceViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Source.objects.all()
    serializer_class = SourceSerializer


class LostReasonViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = LostReason.objects.all()
    serializer_class = LostReasonSerializer


class SectionViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = Section.objects.all()
    serializer_class = SectionSerializer

    def destroy(self, request, *args, **kwargs):
        section = self.get_object()
        if section.leads.filter(is_archived=False).exists():
            return Response(
                {"detail": "Ustunda faol lidlar mavjud. Avval lidlarni boshqa ustunga o'tkazing yoki arxivlang."},
                status=status.HTTP_400_BAD_REQUEST
            )
        return super().destroy(request, *args, **kwargs)


class LeadFormViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = LeadForm.objects.all()
    serializer_class = LeadFormSerializer


class LeadViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    serializer_class = LeadSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['pipeline', 'source', 'status', 'section']
    search_fields = ['name', 'phone', 'email']

    def perform_create(self, serializer):
        org_id = self.get_organization_id()
        if not org_id:
            raise exceptions.ValidationError({"detail": "Organization context is required."})

        kwargs = {'organization_id': org_id}
        if self.request.user.is_authenticated:
            kwargs['created_by'] = self.request.user

        serializer.save(**kwargs)

    def get_queryset(self):
        org_id = self.get_organization_id()
        if not org_id:
            return Lead.objects.none()

        queryset = Lead.objects.filter(organization_id=org_id).select_related(
            'pipeline', 'source', 'section', 'lost_reason', 'created_by'
        )

        if self.action == 'archived':
            return queryset.filter(is_archived=True)

        if self.action not in ['destroy', 'retrieve', 'partial_update', 'update']:
            queryset = queryset.filter(is_archived=False)

        section_param = self.request.query_params.get('section')
        if section_param is not None:
            if section_param.lower() in ('null', 'none', ''):
                queryset = queryset.filter(section__isnull=True)
            else:
                queryset = queryset.filter(section_id=section_param)

        return queryset

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.is_archived:
            instance.delete()
            return Response(status=status.HTTP_204_NO_CONTENT)

        reason = request.query_params.get('reason') or request.data.get('reason') or "O'chirilgan"
        instance.is_archived = True
        instance.archive_reason = reason
        instance.archive_date = timezone.now()
        instance.archived_by = request.user.get_full_name() or request.user.username
        instance.save(update_fields=['is_archived', 'archive_reason', 'archive_date', 'archived_by'])
        return Response({"detail": "Lead archived successfully.", "id": instance.id}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['get'], url_path='archived')
    def archived(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(queryset, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['post'], url_path='bulk-create')
    def bulk_create(self, request):
        leads_data = request.data.get('leads', [])
        if not isinstance(leads_data, list):
            return Response({"detail": "Leads must be a list"}, status=status.HTTP_400_BAD_REQUEST)

        org_id = self.get_organization_id()
        if not org_id:
            return Response({"detail": "Organization context is required."}, status=status.HTTP_400_BAD_REQUEST)

        success_count, failed_count, errors = 0, 0, []

        for idx, item in enumerate(leads_data):
            row_num = item.get('row', idx + 1)
            serializer = self.get_serializer(data=item)
            if serializer.is_valid():
                try:
                    kwargs = {'organization_id': org_id}
                    if request.user.is_authenticated:
                        kwargs['created_by'] = request.user
                    serializer.save(**kwargs)
                    success_count += 1
                except Exception as e:
                    failed_count += 1
                    errors.append({"row": row_num, "name": item.get('name', ''), "detail": str(e)})
            else:
                failed_count += 1
                err_msg = "; ".join([f"{k}: {', '.join(v)}" for k, v in serializer.errors.items()])
                errors.append({"row": row_num, "name": item.get('name', ''), "detail": err_msg})

        return Response({
            "success_count": success_count,
            "failed_count": failed_count,
            "errors": errors
        }, status=status.HTTP_200_OK)


class CreateListRetrieveViewSet(mixins.CreateModelMixin,
                                mixins.ListModelMixin,
                                mixins.RetrieveModelMixin,
                                viewsets.GenericViewSet):
    pass


class CRMActivityViewSet(TenantViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = CRMActivity.objects.all()
    serializer_class = CRMActivitySerializer


class CRMLeadsHistoryViewSet(TenantViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = CRMLeadsHistory.objects.all()
    serializer_class = CRMLeadsHistorySerializer


class CRMLeadLostViewSet(TenantViewSetMixin, CreateListRetrieveViewSet):
    permission_classes = [permissions.IsAuthenticated, IsAdminOrOwnerOrReadOnly]
    permission_page_name = 'Lidlar'
    queryset = CRMLeadLost.objects.all()
    serializer_class = CRMLeadLostSerializer