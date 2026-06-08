from django.db import models as db_models
from rest_framework import exceptions
from organizations.models import Organization
from organizations.permissions import HasOrganizationPagePermission

class TenantViewSetMixin:
    def get_organization_id(self):
        if self.request.user and self.request.user.is_authenticated:
            if not self.request.user.is_superuser:
                return getattr(self.request.user, 'organization_id', None)
        org_id = self.request.query_params.get('org_id')
        if not org_id:
            org_id = self.request.META.get('HTTP_X_ORG_ID') or self.request.headers.get('x-org-id')
        if not org_id and self.request.user and self.request.user.is_authenticated:
            org_id = getattr(self.request.user, 'organization_id', None)
        return org_id

    def get_queryset(self):
        queryset = super().get_queryset()
        model = queryset.model
        if hasattr(model, 'organization'):
            org_id = self.get_organization_id()
            if org_id:
                queryset = queryset.filter(organization_id=org_id)
            else:
                return queryset.none()
        return queryset

    def perform_create(self, serializer):
        model_class = serializer.Meta.model
        if hasattr(model_class, 'organization'):
            org_id = self.get_organization_id()
            if not org_id:
                raise exceptions.ValidationError({"detail": "Organization context is required."})
            try:
                org = Organization.objects.get(id=org_id)
            except Organization.DoesNotExist:
                raise exceptions.ValidationError({"detail": f"Organization with ID {org_id} does not exist."})
            serializer.save(organization=org)
        else:
            serializer.save()

    def get_permissions(self):
        permissions = super().get_permissions()
        if getattr(self, 'permission_page_name', None):
            permissions.append(HasOrganizationPagePermission())
        return permissions