from rest_framework import serializers
from .models import Publication, Category, Views, Notification
import logging
logger = logging.getLogger(__name__)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["name", "id"]

class ViewsSerializer(serializers.ModelSerializer):
    class Meta:
        model = Views
        fields = ['id', 'publication', 'user', 'user_liked', 'user_disliked']
        read_only_fields = ['publication', 'user']

    def get_user(self, obj):
        return obj.user.full_name if obj.user else None

class PublicationSerializer(serializers.ModelSerializer):
    categories = serializers.ListField(
        child=serializers.ChoiceField(choices=Category.CATEGORY_CHOICES),
        write_only=True
    )
    category_labels = serializers.SerializerMethodField(read_only=True)
    view_stats = ViewsSerializer(read_only=True)
    author = serializers.SerializerMethodField(read_only=True)
    status = serializers.CharField(required=False, read_only=False, default='pending')
    editor = serializers.SerializerMethodField(read_only=True)
    keywords = serializers.CharField(required=False, allow_blank=True)
    rejection_note = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    video_file = serializers.FileField(required=False, allow_null=True)  # Add video_file
    class Meta:
        model = Publication
        fields = [
            "id",
            "title",
            "abstract",
            "content",
            "file",
            "video_file",
            "author",
            "categories",
            "category_labels",
            "keywords",
            "views",
            "view_stats",
            "status",
            "editor",
            "publication_date",
            "created_at",
            "updated_at",
            "total_likes",
            "total_dislikes",
            "rejection_note"
        ]
        read_only_fields = [
            "author",
            "views",
            "created_at",
            "updated_at",
            "view_stats",
            "category_labels",
            "id",
            "publication_date",
            "editor"
        ]
        
    def get_total_likes(self, obj):
        return obj.total_likes()

    def get_total_dislikes(self, obj):
        return obj.total_dislikes()

    def create(self, validated_data):
        logger.info(f"Creating publication with validated data: {validated_data}")
        categories = validated_data.pop("categories", [])
        publication = Publication.objects.create(**validated_data)
        for cat in categories:
            category_obj, _ = Category.objects.get_or_create(name=cat)
            publication.categories.add(category_obj)
        return publication

    def update(self, instance, validated_data):
        logger.info(f"Updating publication with validated data: {validated_data}")
        categories = validated_data.pop("categories", None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if categories is not None:
            instance.categories.clear()
            for cat in categories:
                category_obj, _ = Category.objects.get_or_create(name=cat)
                instance.categories.add(category_obj)
        return instance

    def get_category_labels(self, obj):
        return [c.get_name_display() for c in obj.categories.all()]

    def get_author(self, obj):
        return obj.author.full_name

    def get_editor(self, obj):
        return obj.editor.full_name if obj.editor else None

    def validate_title(self, value):
        if not value.strip():
            raise serializers.ValidationError("Title cannot be empty or just whitespace.")
        if len(value) < 10:
            raise serializers.ValidationError("Title must be at least 10 characters long.")
        return value

    def validate_abstract(self, value):
        if not value.strip():
            raise serializers.ValidationError("Abstract cannot be empty or just whitespace.")
        if len(value) < 200:
            raise serializers.ValidationError("Abstract must be at least 200 characters long.")
        if len(value) > 1000:
            raise serializers.ValidationError("Abrast cannot exceed 1000 characters long.")
        return value

    def validate_content(self, value):
        if not value.strip():
            raise serializers.ValidationError("Content cannot be empty or just whitespace.")
        if len(value) < 500:
            raise serializers.ValidationError("Content must be at least 1000 characters long.")
        if len(value) > 10000:
            raise serializers.ValidationError("Content cannot exceed 10000 characters.")
        return value

    def validate_file(self, value):
        if value:
            if value.size > 10 * 1024 * 1024:  # 10MB limit
                raise serializers.ValidationError("File size cannot exceed 10MB.")
            if not value.name.lower().endswith(('.pdf', '.doc', '.docx')):
                raise serializers.ValidationError("Only PDF and Word documents are allowed.")
        return value
    
    def validate_video_file(self, value):  # Add validation for video_file
        if value:
            if value.size > 50 * 1024 * 1024:  # 50MB limit
                raise serializers.ValidationError("Video file size cannot exceed 50MB.")
            if not value.name.lower().endswith(('.mp4', '.avi', '.mov')):
                raise serializers.ValidationError("Only MP4, AVI, or MOV video files are allowed.")
        return value
    
    def validate_keywords(self, value):
        if value:
            if len(value) > 500:
                raise serializers.ValidationError("Keywords cannot exceed 500 characters.")
            # Ensure keywords are comma-separated and trimmed
            keywords = [k.strip() for k in value.split(',') if k.strip()]
            if len(keywords) > 20:
                raise serializers.ValidationError("Cannot have more than 20 keywords.")
            return ','.join(keywords)
        return value
    
class NotificationSerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField(read_only=True)
    related_publication = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = Notification
        fields = ['id', 'user', 'message', 'is_read', 'created_at', 'related_publication']
        read_only_fields = ['created_at', 'related_publication']

    def get_user(self, obj):
        return obj.user.full_name

    def validate_message(self, value):
        if not value.strip():
            raise serializers.ValidationError("Message cannot be empty or just whitespace.")
        if len(value) > 1000:
            raise serializers.ValidationError("Message cannot exceed 1000 characters.")
        return value

    def update(self, instance, validated_data):
        instance.is_read = validated_data.get('is_read', instance.is_read)
        instance.save()
        return instance
    

