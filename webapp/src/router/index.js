import { createRouter, createWebHistory } from 'vue-router'
import FeedView from '@/presentation/views/FeedView.vue'
import EntryDetailView from '@/presentation/views/EntryDetailView.vue'
import UnsubscribeView from '@/presentation/views/UnsubscribeView.vue'

const routes = [
  { path: '/', name: 'feed', component: FeedView },
  { path: '/entry/:id', name: 'entry-detail', component: EntryDetailView, props: true },
  { path: '/unsubscribe', name: 'unsubscribe', component: UnsubscribeView },
]

export const router = createRouter({
  history: createWebHistory(),
  routes,
})
