from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status
from django.shortcuts import get_object_or_404
from .models import Publication, Notification, Category, User, Views
from .serializers import PublicationSerializer, NotificationSerializer, ViewsSerializer
from django.db.models import Q
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from .pagination import StandardResultsPagination, DashboardResultsPagination  # import pagination class



class IsAuthorOrEditor(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        # Editors can view everything
        if request.user.role == 'editor':
            return True

        # Author can view their own publication
        if obj.author == request.user:
            return True

        # Everyone else can only see approved publications
        return obj.status == 'approved'


class PublicationListCreateView(generics.ListCreateAPIView):
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer
    permission_classes = [permissions.IsAuthenticated]
    pagination_class = DashboardResultsPagination  
    


    def get_queryset(self):
        user = self.request.user
        queryset = Publication.objects.all()

        # Filter by keywords if provided in query parameters
        keywords = self.request.query_params.get('keywords', None)
        if keywords:
            # Split keywords by comma and create Q objects for each
            keyword_list = [k.strip() for k in keywords.split(',') if k.strip()]
            keyword_queries = Q()
            for keyword in keyword_list:
                keyword_queries |= (
                    Q(keywords__icontains=keyword) |
                    Q(title__icontains=keyword) |
                    Q(abstract__icontains=keyword)
                )
            queryset = queryset.filter(keyword_queries)

        if user.role == 'editor':
            return queryset
        return queryset.filter(Q(author=user) | Q(status='approved'))


    def perform_create(self, serializer):
        serializer.save(author=self.request.user)

class PublicationDetailView(generics.RetrieveUpdateDestroyAPIView):
    queryset = Publication.objects.all()
    serializer_class = PublicationSerializer
    permission_classes = [permissions.IsAuthenticated, IsAuthorOrEditor]
    pagination_class = StandardResultsPagination  # keep if you need it
    lookup_field = 'pk'  # <-- MUST be a string, not a list

    def get_object(self):
        publication = super().get_object()
        user = self.request.user
        # ensure view record increments only once per user
        if not Views.objects.filter(publication=publication, user=user).exists():
            publication.views += 1
            publication.save(update_fields=["views"])
        return publication

    def perform_update(self, serializer):
        user = self.request.user
        data = self.request.data
        status_value = data.get('status')
        rejection_note = data.get('rejection_note', '').strip() or None

        # Check if the publication is rejected and prevent updates
        if serializer.instance.status == 'rejected' and user.role == 'editor':
            raise ValueError("Rejected publications cannot be changed or updated.")

        # Editor updating status
        if user.role == 'editor' and status_value:
            instance = serializer.save(editor=user, status=status_value)

            if status_value == 'rejected':
                instance.rejection_note = rejection_note
                instance.save(update_fields=['rejection_note'])
                note_msg = f"Reason: {rejection_note}" if rejection_note else "No rejection note provided."
            else:
                instance.rejection_note = None
                instance.save(update_fields=['rejection_note'])
                note_msg = ""

            # Notify the author
            message = (
                f"Your publication '{instance.title}' status changed to '{status_value}' "
                f"at {timezone.now().strftime('%I:%M %p WAT, %B %d, %Y')}."
            )
            Notification.objects.create(
                user=instance.author,
                message=message,
                related_publication=instance
            )

            # Notify other editors (excluding the current editor)
            editors = User.objects.filter(role='editor').exclude(id=user.id)
            for editor in editors:
                Notification.objects.create(
                    user=editor,
                    message=(
                        f"Publication '{instance.title}' status updated to '{status_value}' "
                        f"by {user.full_name} at {timezone.now().strftime('%I:%M %p WAT, %B %d, %Y')}."
                    ),
                    related_publication=instance
                )

            return Response(
                {"message": "Publication status updated successfully.", "rejection_note": rejection_note},
                status=status.HTTP_200_OK
            )

        # Author editing their own publication
        elif user == serializer.instance.author:
            serializer.save()
            return Response({"message": "Publication updated successfully."}, status=status.HTTP_200_OK)

        else:
            raise permissions.PermissionDenied("Only editors can change publication status.")


class NotificationListView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)

class NotificationMarkReadView(generics.UpdateAPIView):
    queryset = Notification.objects.all()
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)
    

class ViewsUpdateView(generics.GenericAPIView):
    serializer_class = ViewsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, *args, **kwargs):
        publication_id = self.kwargs.get("pk")
        publication = get_object_or_404(Publication, pk=publication_id)
        action = request.data.get("action")

        if action not in ["like", "dislike"]:
            return Response(
                {"error": "Invalid action. Use 'like' or 'dislike'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # ✅ FIXED defaults
        view_obj, created = Views.objects.get_or_create(
            publication=publication,
            user=request.user,
            defaults={"user_liked": False, "user_disliked": False}
        )

        if action == "like":
            if view_obj.user_liked:
                return Response({"error": "You have already liked this publication."},
                                status=status.HTTP_400_BAD_REQUEST)
            view_obj.user_liked = True
            view_obj.user_disliked = False

        elif action == "dislike":
            if view_obj.user_disliked:
                return Response({"error": "You have already disliked this publication."},
                                status=status.HTTP_400_BAD_REQUEST)
            view_obj.user_disliked = True
            view_obj.user_liked = False

        view_obj.save(update_fields=["user_liked", "user_disliked"])

        data = {
            "publication_id": publication.id,
            "user": request.user.id,
            "action": action,
            "total_likes": publication.total_likes(),
            "total_dislikes": publication.total_dislikes(),
        }

        return Response(data, status=status.HTTP_200_OK)

class NotificationUnreadView(generics.ListAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated] 

    def get_queryset(self):
        user = self.request.user
        if user.is_anonymous:
            return Notification.objects.none()
        return Notification.objects.filter(user=user, is_read=False).order_by('-created_at')
    
class NotificationMarkAllReadView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        # Get all unread notifications for the current user
        notifications = Notification.objects.filter(user=request.user, is_read=False)
        if not notifications.exists():
            return Response({"message": "No unread notifications to mark as read."}, status=status.HTTP_200_OK)

        # Mark all notifications as read
        notifications.update(is_read=True)
        return Response({"message": "All notifications marked as read."}, status=status.HTTP_200_OK)
