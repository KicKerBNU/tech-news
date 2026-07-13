import { createRouter, createWebHistory } from 'vue-router'
import FeedView from '@/presentation/views/FeedView.vue'
import EntryDetailView from '@/presentation/views/EntryDetailView.vue'

const routes = [
  { path: '/', name: 'feed', component: FeedView },
  { path: '/entry/:id', name: 'entry-detail', component: EntryDetailView, props: true },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
