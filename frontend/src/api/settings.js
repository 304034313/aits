import api from './index'

export function getMenuConfig() {
  return api.get('/settings/menu-config/')
}

export function updateMenuConfig(module, menuItems) {
  return api.put(`/settings/menu-config/${module}/`, { menu_items: menuItems })
}

export function resetMenuConfig(module) {
  return api.post('/settings/menu-config-reset/', module ? { module } : {})
}
