import shutil
import tempfile

from django import forms
from django.conf import settings
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from ..models import Follow, Group, Post, User

TEMP_MEDIA_ROOT = tempfile.mkdtemp(dir=settings.BASE_DIR)


@override_settings(MEDIA_ROOT=TEMP_MEDIA_ROOT)
class PostPagesTests(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username='auth')
        cls.user2 = User.objects.create_user(username='bauman1922')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test_slug',
            description='Тестовое описание',
        )

        cls.group_2 = Group.objects.create(
            title='Тестовая группа 2',
            slug='test_slug_2',
            description='Тестовое описание 2',
        )
        small_gif = (
            b'\x47\x49\x46\x38\x39\x61\x02\x00'
            b'\x01\x00\x80\x00\x00\x00\x00\x00'
            b'\xFF\xFF\xFF\x21\xF9\x04\x00\x00'
            b'\x00\x00\x00\x2C\x00\x00\x00\x00'
            b'\x02\x00\x01\x00\x00\x02\x02\x0C'
            b'\x0A\x00\x3B'
        )
        cls.uploaded = SimpleUploadedFile(
            name='small.gif',
            content=small_gif,
            content_type='image/gif'
        )

        cls.post = Post.objects.create(
            author=cls.user,
            text='Тестовая запись',
            group=cls.group,
            image=cls.uploaded,
        )

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(TEMP_MEDIA_ROOT, ignore_errors=True)

    def setUp(self):
        self.guest_client = Client()
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)
        self.authorized_user = User.objects.create_user(username='warrior')
        self.authorized_client_1 = Client()
        self.authorized_client_1.force_login(self.authorized_user)
        cache.clear()

    def test_pages_uses_correct_template(self):
        """URL-адрес использует соответствующий шаблон."""
        templates_pages_names = {
            reverse('posts:index'): 'posts/index.html',
            reverse('posts:group_list', kwargs={'slug': self.group.slug}
                    ): 'posts/group_list.html',
            reverse('posts:profile', kwargs={'username': self.user.username}
                    ): 'posts/profile.html',
            reverse('posts:post_detail', kwargs={'post_id': self.post.id}
                    ): 'posts/post_detail.html',
            reverse('posts:post_create'): 'posts/create_post.html',
            reverse('posts:post_edit', kwargs={'post_id': self.post.id}
                    ): 'posts/create_post.html',
        }
        for reverse_name, template in templates_pages_names.items():
            with self.subTest(template=template):
                response = self.authorized_client.get(reverse_name)
                self.assertTemplateUsed(response, template)

    def test_show_correct_context(self):
        """Шаблоны сформированы с правильным контекстом."""
        templates_page_names = [
            reverse('posts:index'),
            reverse('posts:group_list', kwargs={'slug': self.group.slug}),
            reverse('posts:profile', kwargs={'username': self.user.username}),
            reverse('posts:post_detail', kwargs={'post_id': self.post.id}),
        ]
        for reverse_name in templates_page_names:
            with self.subTest(reverse_name=reverse_name):
                response = self.authorized_client.get(reverse_name)
                if reverse_name == reverse(
                   'posts:post_detail', kwargs={'post_id': self.post.id}):
                    first_object = response.context['post']
                else:
                    first_object = response.context['page_obj'][0]
                post_text = first_object.text
                post_image = first_object.image
                self.assertEqual(post_text, 'Тестовая запись')
                self.assertEqual(post_image, 'posts/small.gif')

    def test_post_with_image(self):
        """При отправке поста с картинкой создаётся запись в базе данных."""
        Post.objects.create(
            author=self.user,
            text='Пост с картинкой',
            group=self.group,
            image=self.uploaded,
        )
        self.assertTrue(Post.objects.filter(text='Пост с картинкой').exists())

    def test_create_or_edit_post_page_show_correct_context(self):
        """Шаблон create_post/edit сформирован с правильным контекстом."""
        templates_page_names = [
            reverse('posts:post_create'),
            reverse('posts:post_edit', kwargs={'post_id': self.post.id}),
        ]
        form_fields = {
            'text': forms.fields.CharField,
            'group': forms.fields.ChoiceField,
        }

        for template in templates_page_names:
            with self.subTest(template=template):
                response = self.authorized_client.get(template)
                for value, expected in form_fields.items():
                    with self.subTest(value=value):
                        form_field = response.context.get(
                            'form').fields.get(value)
                        self.assertIsInstance(form_field, expected)

    def test_post_another_group(self):
        """Пост не попал в другую группу."""
        response = self.authorized_client.get(
            reverse('posts:group_list', kwargs={'slug': self.group_2.slug}))
        self.assertEqual(response.context['page_obj'].object_list.count(), 0)

    def test_comment_appears_on_post_page(self):
        """Комментарий появляется на странице поста."""
        form_data = {
            'text': 'Комментарий к посту',
        }
        self.authorized_client.post(
            reverse('posts:add_comment', kwargs={'post_id': self.post.id}),
            data=form_data,
        )
        response = self.guest_client.get(
            reverse('posts:post_detail', kwargs={'post_id': self.post.id})
        )
        self.assertEqual(
            response.context['comments'][0].text, 'Комментарий к посту')

    def test_cache_index_page(self):
        """Проверка хранения и очищения кэша для index."""
        cache.clear()
        post = Post.objects.create(
            author=self.user,
            group=self.group,
            text='test_text'
        )
        response = self.guest_client.get(reverse('posts:index'))
        self.assertIn(
            post.text, str(response.content))
        response_1_authorized = self.authorized_client.get(
            reverse('posts:index'))
        response_1_guest = self.guest_client.get(
            reverse('posts:index'))
        Post.objects.filter(text=post.text).delete()
        self.assertFalse(
            Post.objects.filter(text=post.text).exists())
        response_2_authorized = self.authorized_client.get(
            reverse('posts:index'))
        response_2_guest = self.guest_client.get(
            reverse('posts:index'))
        self.assertEqual(
            response_1_authorized.content, response_2_authorized.content)
        self.assertEqual(
            response_1_guest.content, response_2_guest.content)
        cache.clear()
        response_3_authorized = self.authorized_client.get(
            reverse('posts:index'))
        response_3_guest = self.guest_client.get(
            reverse('posts:index'))
        self.assertNotEqual(
            response_1_authorized.content, response_3_authorized.content)
        self.assertNotEqual(
            response_1_guest.content, response_3_guest.content)

    def test_authorized_user_can_subscribe(self):
        """Авторизованный пользователь может
        подписываться на других пользователей."""
        count_1 = Follow.objects.all().count()
        self.authorized_client.get(reverse(
            'posts:profile_follow', kwargs={'username': self.user2.username}))
        count_2 = Follow.objects.all().count()
        self.assertEqual(count_1 + 1, count_2)

    def test_authorized_user_delete_subscriptions(self):
        """Авторизованный пользователь может удалять
        пользователей из подписок."""
        count_1 = Follow.objects.all().count()
        self.authorized_client.get(reverse(
            'posts:profile_follow', kwargs={'username': self.user2.username}))
        self.authorized_client.get(reverse(
            'posts:profile_unfollow',
            kwargs={'username': self.user2.username}))
        count_2 = Follow.objects.all().count()
        self.assertEqual(count_2, count_1)

    def test_new_post_appears_in_feed(self):
        """Новая запись пользователя появляется
        в ленте тех, кто на него подписан."""
        post = Post.objects.create(
            author=self.user,
            group=self.group,
            text='test_text'
        )
        self.authorized_client_1.get(
            reverse('posts:profile_follow',
                    kwargs={'username': self.user.username}))
        response = self.authorized_client_1.get(reverse('posts:follow_index'))
        object_list = response.context.get('page_obj')
        self.assertIn(post, object_list)

    def test_new_post_appears_in_feed(self):
        """Новая запись пользователя не появляется
          в ленте тех, кто не подписан."""
        post = Post.objects.create(
            author=self.user,
            group=self.group,
            text='test_text'
        )
        self.authorized_client_1.get(
            reverse('posts:profile_follow',
                    kwargs={'username': self.user.username}))
        response = self.authorized_client.get(reverse('posts:follow_index'))
        object_list = response.context.get('page_obj')
        self.assertNotIn(post, object_list)

    def test_check_group_in_pages(self):
        """Пост появляется на главной странице сайта
        и на странице выбранной группы."""
        post = Post.objects.get(group=self.post.group)
        page_list = [
            reverse('posts:index'),
            reverse('posts:group_list', kwargs={'slug': self.group.slug}),
        ]
        for page in page_list:
            response = self.guest_client.get(page)
            object_list = response.context.get('page_obj')
            self.assertIn(post, object_list)

    def test_authorized_user_comment(self):
        """Только авторизированный пользователь может комментировать посты."""
        form_data = {
            'text': 'Комментарий к посту',
        }
        response = self.authorized_client.post(reverse(
            'posts:add_comment', kwargs={'post_id': self.post.id}),
            follow=True,
            data=form_data)
        self.assertContains(response, 'Комментарий к посту')


class PaginatorViewsTest(TestCase):
    """Проверяем пагинатор в шаблонах
    index.html, post_list.html,profile.html."""
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.user = User.objects.create_user(username='auth')
        cls.group = Group.objects.create(
            title='Тестовая группа',
            slug='test_slug',
            description='Тестовое описание',
        )
        cls.posts = []
        for i in range(13):
            cls.posts.append(Post(
                author=cls.user,
                text=f'Тестовая запись {i}',
                group=cls.group))
        Post.objects.bulk_create(cls.posts)

    def setUp(self):
        self.guest_client = Client()
        self.authorized_client = Client()
        self.authorized_client.force_login(self.user)
        cache.clear()

    def test_first_page_contains_ten_posts(self):
        url_names = {
            reverse('posts:index'),
            reverse('posts:group_list', kwargs={'slug': self.group.slug}),
            reverse('posts:profile', kwargs={'username': self.user.username}),
        }
        for reverse_name in url_names:
            with self.subTest(reverse_name=reverse_name):
                response = self.guest_client.get(reverse_name)
                self.assertEqual(
                    response.context['page_obj'].paginator.page('1').
                    object_list.count(), 10)

    def test_second_page_contains_three_posts(self):
        url_names = {
            reverse('posts:index'),
            reverse('posts:group_list', kwargs={'slug': self.group.slug}),
            reverse('posts:profile', kwargs={'username': self.user.username}),
        }
        for reverse_name in url_names:
            with self.subTest(reverse_name=reverse_name):
                response = self.guest_client.get(reverse_name + '?page=2')
                self.assertEqual(
                    response.context['page_obj'].paginator.page('2').
                    object_list.count(), 3)
