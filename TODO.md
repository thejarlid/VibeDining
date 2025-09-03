# TODO

## short term 
[] scraping api
[] setup indexing on supabase with pgvector
[] Add data freshness
[] web search tool
[] More deterministic graph-based agent
[] Need to make agent faster -> retrieval is too slow
[x] Get user's current location to help with ambiguoius requests
[] Stream responses back to the user so that its not just waiting 
    [] Ideally also print out the thinking path/plan so they know what's happening
[] return structured output/json instead of responding with a markdown message that is then printed. A structured output would allow us to format things on the frontend nicely and also then make a map interface

## Longterm backlog
[] Add ability to have users
[] Users can upload and share their own maps lists
[] lists/agents can be shareable with friends
[] agent can have context to search over multiple lists or specific lists - default is all data for a user 
[] queue user's requests so we don't overload my openai limit 
