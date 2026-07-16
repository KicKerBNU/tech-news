export async function subscribeToNewsletter(email) {
  const response = await fetch('/.netlify/functions/subscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.error || 'Subscription failed')
  }
  return payload.message
}

export async function unsubscribeFromNewsletter(email, sig) {
  const response = await fetch('/.netlify/functions/unsubscribe', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, sig }),
  })

  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.error || 'Unsubscribe failed')
  }
  return payload.message
}
